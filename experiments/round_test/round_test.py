#encoding:utf8
import os
import sys
import pickle
import matplotlib.pyplot as plt
import pdb
import time
import json
import random
import numpy as np

from randomwalk.random_walker import RandomWalker
from QTdata.loadQTdata import QTloader


def Test1(target_label = 'P', num_training = 25):
    '''Test case 1: random walk.'''
    qt = QTloader()
    record_list = qt.getreclist()
    training_list = random.sample(record_list, num_training)
    testing_list = list(set(record_list) - set(training_list))

    random_forest_config = dict(
            max_depth = 10)
    walker = RandomWalker(target_label = target_label,
            random_forest_config = random_forest_config)

    start_time = time.time()
    for record_name in training_list:
        print 'Collecting features from record %s.' % record_name
        sig = qt.load(record_name)
        walker.collect_training_data(sig['sig'], qt.getExpert(record_name))
    print 'random forest start training...'
    walker.training()
    print 'trianing used %.3f seconds' % (time.time() - start_time)

    for record_name in testing_list:
        sig = qt.load(record_name)
        raw_sig = sig['sig']

        seed_position = random.randint(100, len(raw_sig) - 100)
        plt.figure(1)
        plt.clf()
        plt.plot(sig['sig'], label = record_name)
        plt.title(target_label)
        for ti in xrange(0, 20):
            seed_position += random.randint(1,200)
            print 'testing...(position: %d)' % seed_position
            start_time = time.time()
            results = walker.testing_walk(sig['sig'], seed_position, iterations = 100,
                    stepsize = 10)
            print 'testing finished in %.3f seconds.' % (time.time() - start_time)

            pos_list, values = zip(*results)
            predict_pos = np.mean(pos_list[len(pos_list) / 2:])
            
            # amp_list = [raw_sig[int(x)] for x in pos_list]
            amp_list = []
            bias = raw_sig[pos_list[0]]
            for pos in pos_list:
                amp_list.append(bias)
                bias -= 0.01

            plt.plot(predict_pos,
                    raw_sig[int(predict_pos)],
                    'ro',
                    markersize = 14,
                    label = 'predict position')
            plt.plot(pos_list, amp_list, 'r',
                    label = 'walk path',
                    markersize = 3,
                    linewidth = 8,
                    alpha = 0.3)
            plt.xlim(min(pos_list) - 100, max(pos_list) + 100)
            plt.grid(True)
            plt.legend()
            plt.show(block = False)
            pdb.set_trace()

def testing(random_walker, raw_sig, seed_step_size = 200):
    result_list = list()
    start_time = time.time()
    for seed_position in xrange(0, len(raw_sig), seed_step_size):
        sys.stdout.write('\rTesting: %06d samples left.' % (len(raw_sig) - 1 - seed_position))
        sys.stdout.flush()

        results = random_walker.testing_walk(raw_sig,
                seed_position,
                iterations = 100,
                stepsize = 10)
        pos_list, values = zip(*results)
        predict_pos = np.mean(pos_list[len(pos_list) / 2:])
        confidence = 1.0
        result_list.append((predict_pos, random_walker.target_label, confidence, pos_list))
    print 'testing finished in %.3f seconds.' % (time.time() - start_time)
    return result_list

def TrainingModels(target_label, model_file_name, training_list, random_pattern_path = None):
    '''Randomly select num_training records to train, and test others.'''
    qt = QTloader()
    record_list = qt.getreclist()
    testing_list = list(set(record_list) - set(training_list))

    random_forest_config = dict(
            max_depth = 10)
    walker = RandomWalker(target_label = target_label,
            random_forest_config = random_forest_config,
            random_pattern_file_name = random_pattern_path)

    start_time = time.time()
    for record_name in training_list:
        print 'Collecting features from record %s.' % record_name
        sig = qt.load(record_name)
        walker.collect_training_data(sig['sig'], qt.getExpert(record_name))
    print 'Random forest start training(%s)...' % target_label
    print 'Training matrix shape:(%d, %d)' %  (len(walker.training_data), len(walker.training_data[0]))
    walker.training()
    print 'trianing used %.3f seconds' % (time.time() - start_time)

    import joblib
    start_time = time.time()
    walker.save_model(model_file_name)
    print 'Serializing model time cost %f' % (time.time() - start_time)





def randomTraining(root_folder = 'models/round1', num_training = 75,random_pattern_path = 'models/random_pattern.json'):
    label_list = ['P', 'Ponset', 'Poffset',
            'T', 'Toffset',
            'Ronset', 'Roffset']
    
    if os.path.exists(root_folder) == False:
        os.mkdir(root_folder)

    # Refresh training list
    trianing_list = list()
    qt = QTloader()
    record_list = qt.getreclist()
    must_train_list = [
        "sel35", 
        "sel36", 
        "sel31", 
        "sel38", 
        "sel39", 
        "sel820", 
        "sel51", 
        "sele0104", 
        "sele0107", 
        "sel223", 
        "sele0607", 
        "sel102", 
        "sele0409", 
        "sel41", 
        "sel40", 
        "sel43", 
        "sel42", 
        "sel45", 
        "sel48", 
        "sele0133", 
        "sele0116", 
        "sel14172", 
        "sele0111", 
        "sel213", 
        "sel14157", 
        "sel301"
            ]
    num_training -= len(must_train_list)
    record_list = list(set(record_list) - set(must_train_list))
    training_list = must_train_list
    if num_training > 0:
        training_list.extend(random.sample(record_list, num_training))
    # Save training list
    with open(os.path.join(root_folder, 'training_list.json'), 'w') as fout:
        json.dump(training_list, fout, indent = 4)

    # Train Models with multiprocessing
    from multiprocessing import Process
    process_list = list()
    for target_label in label_list:
        model_file_name = os.path.join(root_folder, '%s.mdl' % target_label)
        # TrainingModels(target_label, model_file_name, training_list, random_pattern_path = random_pattern_path)
        p1 = Process(target = TrainingModels, args = (target_label, model_file_name, training_list, random_pattern_path))
        process_list.append(p1)
        p1.start()

    for process_bit in process_list:
        process_bit.join()
    
    

    # Testing
    testing_list = list(set(qt.getreclist()) - set(training_list))
    saveresultpath = os.path.join(root_folder, 'results')
    if os.path.exists(saveresultpath) == False:
        os.mkdir(saveresultpath)
    from record_test import RoundTesting
    RoundTesting(saveresultpath, testing_list, model_folder = root_folder, pattern_filename = random_pattern_path)


if __name__ == '__main__':
    random_pattern_path = 'hiking_real/random_pattern.json'
    for rnd in xrange(1, 31):
        randomTraining('hiking_real/round%d' % rnd, random_pattern_path = random_pattern_path)
