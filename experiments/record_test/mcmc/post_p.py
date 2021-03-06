#encoding:utf8
import os, sys, pdb, json
import numpy as np
import matplotlib.pyplot as plt

import gaussian_model as P_model_Gaussian
import numpy as np
import math
from pymc import MCMC
import scipy.signal as signal
from randomwalk.changgengLoader import ECGLoader as cLoader


def compare_annot(a1, a2):
    if a1[0] != a2[0]:
        return int(a1[0] - a2[0])
    elif a2[1] == 'P' and a1[1] == 'Poffset':
        return 1
    else:
        return -1
        
def post_p(raw_sig, annots, fs):
    '''Post processing for P wave.'''
    other_annots = filter(lambda x: x[1][0] != 'P' and x[1] != 'Ronset', annots)
    annots = filter(lambda x: x[1][0] == 'P' or x[1] == 'Ronset', annots)
    annots.sort(key = lambda x:x, cmp = compare_annot)
    
    for ind in xrange(1, len(annots) - 1):
        pos, label = annots[ind]
        if label == 'P':
            if annots[ind-1][1] != 'Ponset' or annots[ind + 1][1] != 'Poffset':
                print 'Warning: mis-matched P in pos %d' % pos
                continue
            ponset = int(annots[ind-1][0])
            poffset = int(annots[ind + 1][0])
            

            if np.argmax(raw_sig[ponset:poffset + 1]) + ponset != pos:
                pos = int(np.argmax(raw_sig[ponset:poffset + 1]) + ponset)
            pos = int(pos)

            # Poffset too close to pos
            if poffset - pos < 10 / 500.0 * fs:
                right_bound = int(min(len(raw_sig), pos + 35 / 500.0 * fs + 1))
                poffset = pos + np.argmin(raw_sig[pos:right_bound])

            # Ponset too close to pos
            if abs(ponset - pos) < 10 / 500.0 * fs:
                left_bound = int(max(0, pos - 35 / 500.0 * fs))
                ponset = left_bound + np.argmin(raw_sig[left_bound:pos])



            annots[ind][0] = pos
            annots[ind-1][0] = ponset
            annots[ind + 1][0] = poffset
    annots.extend(other_annots)
    return annots

            
def post_p_mcmc(raw_sig, annots, fs, expand_width = 20):
    '''Post processing for P wave with MCMC.'''
    if abs(fs - 500.0) > 1e-6:
        raise Exception('fs != 500, we cannot handle that, sorry.')

    annots = post_p(raw_sig, annots, fs)
    annots.sort(key = lambda x:x[0])
    
    x_range_list = list()
    x_range_start = None
    for ind in xrange(0, len(annots)):
        pos, label = annots[ind]
        if label == 'Ponset':
            x_range_start = pos - expand_width
        elif label == 'Poffset':
            if x_range_start is not None:
                x_range_list.append((x_range_start, pos + expand_width))
            x_range_start = None
            

    
    # MCMC testing
    for x_range in x_range_list:
        ponset, p, poffset = None, None, None
        for ind in xrange(0, len(annots)):
            pos, label = annots[ind]
            if pos < x_range[0] or pos > x_range[1]:
                continue
            if label == 'Poffset':
                poffset = ind
            elif label == 'P':
                p = ind
            elif label == 'Ponset':
                ponset = ind
        if None in [ponset, p, poffset]:
            continue

        Pannots = map(lambda x:[x[0] - x_range[0], x[1]],
                [annots[ind] for ind in [ponset, p, poffset]])
        ecg_segment = raw_sig[x_range[0]:x_range[1]]
        if len(ecg_segment) == 0:
            continue
        results = p_segment_mcmc(ecg_segment, Pannots, 500.0)
        annots[ponset][0] = results['Ponset'] + x_range[0]
        annots[poffset][0] = results['Poffset'] + x_range[0]
        
    return annots


def p_segment_mcmc(
        filtered_sig,
        annots,
        fs,
        step = 2,
        iter_count = 4000,
        burn_count = 2000,
        max_hermit_level = 4,
        savefig_path = None,
        figID = None,
        ):
    '''Detect and returns P wave detection results.
        Note:
            * Input is a segment contains only P wave.
            * This function returns None when detection fails.
    '''
    filtered_sig = np.array(filtered_sig)
    # Normalization
    max_val = np.max(filtered_sig)
    min_val = np.min(filtered_sig)
    if (max_val - min_val) > 1e-6:
        filtered_sig = (filtered_sig - min_val) / (max_val - min_val)


    raw_sig = filtered_sig
    sig_seg = raw_sig
    

    p_model = P_model_Gaussian.MakeModel(sig_seg,
            annots,
            max_hermit_level = max_hermit_level)
    M = MCMC(p_model)

    M.sample(iter = iter_count, burn = burn_count, thin = 10)

    # retrieve parameters
    hermit_coefs = list()
    for h_ind in xrange(0, P_model_Gaussian.HermitFunction_max_level):
        hermit_value = np.mean(M.trace('hc%d' % h_ind)[:])
        hermit_coefs.append(hermit_value)

    fitting_curve = np.zeros(len(sig_seg),)
    for level, coef in zip(xrange(0, max_hermit_level), hermit_coefs):
        fitting_curve += P_model_Gaussian.HermitFunction(level, len(sig_seg)) * coef



    # Gaussian

    pos_ponset = None
    pos_p = None
    pos_poffset = None
    for pos, label in annots:
        if label == 'Ponset':
            pos_ponset = pos
        elif label == 'P':
            pos_p = pos
        elif label == 'Poffset':
            pos_poffset = pos

    gaussian_curve = np.zeros(len(sig_seg),)
    common_length = len(sig_seg)
    g_amp = np.mean(M.trace('g_amp')[:])
    g_sigma = np.mean(M.trace('g_sigma')[:])
    g_dc = np.mean(M.trace('dc')[:])
    gaussian_curve = P_model_Gaussian.GetGaussianPwave(len(sig_seg) * 2, g_amp, g_sigma / 3, g_dc)
    
    gaussian_segment = gaussian_curve[common_length - pos_p:2 * common_length - pos_p]
    baseline_curve = fitting_curve + g_dc
    baseline_curve = baseline_curve.tolist()
    fitting_curve += gaussian_segment
    
    # Compute results
    results = dict(P=pos_p)
    meet_threshold = 0.07
    for ind in xrange(0, len(fitting_curve)):
        if ('Ponset' not in results and
                abs(fitting_curve[ind] - baseline_curve[ind]) >= meet_threshold):
            results['Ponset'] = ind
        elif ('Ponset' in results and
                abs(fitting_curve[ind] - baseline_curve[ind]) >= meet_threshold):
            results['Poffset'] = ind
    # If not found
    if 'Ponset' not in results:
        results['Ponset'] = pos_ponset
        results['Poffset'] = pos_poffset
    elif 'Poffset' not in results:
        results['Poffset'] = pos_poffset

    return results
        
def test_cmp():
    # Not working...
    annots = [(1, 'P'), (1, 'Ponset'), (1, 'Poffset'), (1, 'P')]
    annots.sort(cmp = compare_annot)

    print annots

def crop_data_for_swt(rawsig):
    '''Padding zeros to make the length of the signal to 2^N.'''
    # crop rawsig
    base2 = 1
    N_data = len(rawsig)
    if len(rawsig)<=1:
        raise Exception('len(rawsig)={}, not enough for swt!', len(rawsig))
    crop_len = base2
    while base2<N_data:
        if base2*2>=N_data:
            crop_len = base2*2
            break
        base2*=2
    # Extending this signal input with its tail element.
    if N_data< crop_len:
        rawsig += [rawsig[-1],]*(crop_len-N_data)
    return rawsig

def post_p_wt(raw_sig, annots, fs):
    '''Post-processing of P wave with wavelet transform.'''
    import pywt, math
    annots = post_p(raw_sig, annots, fs)
    annots.sort(key = lambda x:x[0])

    raw_sig = crop_data_for_swt(raw_sig.tolist())
    
    a0 = 0.3133
    a1 = 2.0 * math.sqrt(2.0 * math.pi)
    dec_lo = (a0, a0 * 3, a0 * 3, a0)
    dec_hi = (0, a1, -a1, 0)
    # rec_lo = (0, a0, a0 * 3, a0 * 3, a0)
    # rec_hi = (0, 0, -a1, a1, 0)
    rec_lo = (0, 0, 0, 0)
    rec_hi = (0, 0, 0, 0)

    filter_bank = [dec_lo, dec_hi, rec_lo, rec_hi]
    print filter_bank
    wavelet_q = pywt.Wavelet('q_wave', filter_bank = filter_bank)

    # coefs = pywt.swt(raw_sig, 'bior1.3', level = 7)
    coefs = pywt.swt(raw_sig, wavelet_q, level = 7)


    plt.figure(1)

    m0 = min(raw_sig)
    m1 = max(raw_sig)
    # print 'm1 %f, m0 %f' % (m1, m0)
    raw_sig = [(x - m0)/ (m1 - m0) for x in raw_sig]
    plt.plot(raw_sig, label = 'ECG')
    
    for ind in xrange(-4, -6, -1):
        wt_signal = coefs[ind][1]
        m0 = min(wt_signal)
        m1 = max(wt_signal)
        # print 'm1 %f, m0 %f' % (m1, m0)
        wt_signal = [(x - m0)/ (m1 - m0) for x in wt_signal]
        plt.plot(wt_signal, label = 'WT level %d' % ind)
    
    plt.grid(True)
    plt.legend()
    plt.show()
    
    return []
    

