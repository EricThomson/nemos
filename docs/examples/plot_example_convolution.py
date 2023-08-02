"""
One-dimensional convolutions
"""

# %%
# ## Generate synthetic data
# Generate some simulated spike counts.

import numpy as np
import matplotlib.pylab as plt
import matplotlib.patches as patches
from neurostatslib.utils import convolve_1d_trials, nan_pad_conv

np.random.seed(10)
ws = 7
# samples
n_samples = 100

# number of neurons
n_neurons = 1
spk = np.random.poisson(lam=0.1, size=(n_neurons, n_samples))

# add borders (extreme case, general border effect are represented)
spk[0, 0] = 1
spk[0, 3] = 1
spk[0, -1] = 1
spk[0, -4] = 1


# %%
# ## Convolution in `"valid"` mode
# Generate and plot a filter, then execute a convolution in "valid" mode for all trials and neurons.
# !!! info
#     The `"valid"` mode of convolution only calculates the product when the two input vectors overlap completely,
#     avoiding border artifacts. The outcome of such a convolution will
#     be an array of `max(M,N) - min(M,N) + 1` elements in length, where `M` and `N` represent the number
#     of elements in the arrays being convolved. For more detailed information on this,
#     see [jax.numpy.convolve](https://jax.readthedocs.io/en/latest/_autosummary/jax.numpy.convolve.html).


# create two filters
w = np.vstack([
    np.ones((1, ws)),
    np.hstack([np.arange(ws//2 + ws % 2),
               np.arange(ws//2 - 1, -1, -1)]).reshape(1, -1)
                ])
plt.plot(w.T)

# convolve the spikes:
# the function requires an iterable (one element per trial)
# and returns a list of convolutions

spk_conv = convolve_1d_trials(w, [spk, np.zeros((1,20))])
print(f"Shape of spk: {spk.shape}\nShape of w: {w.shape}")

# valid convolution should be of shape n_samples - ws + 1
print(f"Shape of the convolution output: {spk_conv[0].shape}")

# %%
# ## Causal, Anti-Causal, and Acausal filters
# NaN padding appropriately the output of the convolution allows to model  causal, anti-causal and acausal filters.
# A causal filter captures how an event or task variable influences the future firing-rate.
# An example usage case would be that of characterizing the refractory period of a neuron
# (i.e. the drop in firing rate  immediately after a spike event). Another example could be characterizing how
# the current position of an animal in a maze would affect its future spiking activity.
#
# On the other hand, if we are interested in capturing the firing rate modulation before an event occurs we may want
# to use an anti-causal filter. An example of that may be the preparatory activity of pre-motor cortex that happens
# before a movement is initiated (here the event is. "movement onset").
#
# Finally, if one wants to capture both causal
# and anti-causal effects one should use the acausal filters.
# Below we provide a function that pads the convolution output for the different filter types.


# pad according to the causal direction of the filter, after squeeze, the dimension is (n_filters, n_samples)
spk_causal_utils = np.squeeze(nan_pad_conv(spk_conv, ws, filter_type="causal")[0])
spk_anticausal_utils = np.squeeze(nan_pad_conv(spk_conv, ws, filter_type="anti-causal")[0])
spk_acausal_utils = np.squeeze(nan_pad_conv(spk_conv, ws, filter_type="acausal")[0])


# %%
# Plot the results

# NaN padded area
rect_causal = patches.Rectangle((0,0), ws, 3, alpha=0.3, color='grey')
rect_anticausal = patches.Rectangle((len(spk[0])-ws, 0), ws, 3, alpha=0.3, color='grey')
rect_acausal_left = patches.Rectangle((0, 0), (ws-1)//2, 3, alpha=0.3, color='grey')
rect_acausal_right = patches.Rectangle((len(spk[0]) - (ws-1)//2, 0), (ws-1)//2, 3, alpha=0.3, color='grey')


plt.figure(figsize=(6,4))

ax = plt.subplot(311)

plt.title('valid + nan-pad')
ax.add_patch(rect_causal)
plt.vlines(np.arange(spk.shape[1]), 0, spk[0], color='k')
plt.plot(np.arange(spk.shape[1]), spk_causal_utils.T)
plt.ylabel('causal')

ax = plt.subplot(312)
ax.add_patch(rect_anticausal)
plt.vlines(np.arange(spk.shape[1]), 0, spk[0], color='k')
plt.plot(np.arange(spk.shape[1]), spk_anticausal_utils.T)
plt.ylabel('anti-causal')

ax=plt.subplot(313)
ax.add_patch(rect_acausal_left)
ax.add_patch(rect_acausal_right)
plt.vlines(np.arange(spk.shape[1]), 0, spk[0], color='k')
plt.plot(np.arange(spk.shape[1]), spk_acausal_utils.T)
plt.ylabel('acausal')
plt.tight_layout()
