"""Noise model classes for GLMs."""

import abc
from typing import Callable, Union

import jax
import jax.numpy as jnp

from .base_class import Base

KeyArray = Union[jnp.ndarray, jax.random.PRNGKeyArray]

__all__ = ["PoissonNoiseModel"]


def __dir__():
    return __all__


class NoiseModel(Base, abc.ABC):
    """
    Abstract noise model class for neural data processing.

    This is an abstract base class used to implement noise models for neural data.
    Specific noise models that inherit from this class should define their versions
    of the abstract methods: negative_log_likelihood, emission_probability, and
    residual_deviance.

    Attributes
    ----------
    FLOAT_EPS :
        A small value used to ensure numerical stability. Set to the machine epsilon for float32.
    inverse_link_function :
        A function that transforms a set of predictors to the domain of the model parameter.

    See Also
    --------
    [PoissonNoiseModel](./#neurostatslib.noise_model.PoissonNoiseModel) : A specific implementation of a
    noise model using the Poisson distribution.
    """

    FLOAT_EPS = jnp.finfo(float).eps

    def __init__(self, inverse_link_function: Callable, **kwargs):
        super().__init__(**kwargs)
        self.inverse_link_function = inverse_link_function
        self.scale = 1.0

    @property
    def inverse_link_function(self):
        """Getter for the inverse link function for the model."""
        return self._inverse_link_function

    @inverse_link_function.setter
    def inverse_link_function(self, inverse_link_function: Callable):
        """Setter for the inverse link function for the model."""
        self._check_inverse_link_function(inverse_link_function)
        self._inverse_link_function = inverse_link_function

    @property
    def scale(self):
        """Getter for the scale parameter of the model."""
        return self._scale

    @scale.setter
    def scale(self, value: Union[int, float]):
        """Setter for the scale parameter of the model."""
        if not isinstance(value, (int, float)):
            raise ValueError("The `scale` parameter must be of numeric type.")
        self._scale = value

    @staticmethod
    def _check_inverse_link_function(inverse_link_function: Callable):
        """
        Check if the provided inverse_link_function is usable.

        This function verifies if the inverse link function:
        1. Is callable
        2. Returns a jax.numpy.ndarray
        3. Is differentiable (via jax)

        Parameters
        ----------
        inverse_link_function :
            The function to be checked.

        Raises
        ------
        TypeError
            If the function is not callable, does not return a jax.numpy.ndarray,
            or is not differentiable.
        """

        # check that it's callable
        if not callable(inverse_link_function):
            raise TypeError("The `inverse_link_function` function must be a Callable!")

        # check if the function returns a jax array for a 1D array
        array_out = inverse_link_function(jnp.array([1.0, 2.0, 3.0]))
        if not isinstance(array_out, jnp.ndarray):
            raise TypeError(
                "The `inverse_link_function` must return a jax.numpy.ndarray!"
            )

        # Optionally: Check for scalar input
        scalar_out = inverse_link_function(1.0)
        if not isinstance(scalar_out, (jnp.ndarray, float, int)):
            raise TypeError(
                "The `inverse_link_function` must handle scalar inputs correctly and return a scalar or a "
                "jax.numpy.ndarray!"
            )

        # check for autodiff
        try:
            gradient_fn = jax.grad(inverse_link_function)
            gradient_fn(1.0)
        except Exception as e:
            raise TypeError(
                f"The `inverse_link_function` function cannot be differentiated. Error: {e}"
            )

    @abc.abstractmethod
    def negative_log_likelihood(self, predicted_rate, y):
        r"""Compute the noise model negative log-likelihood.

        This computes the negative log-likelihood of the predicted rates
        for the observed neural activity up to a constant.

        Parameters
        ----------
        predicted_rate :
            The predicted rate of the current model. Shape (n_time_bins, n_neurons).
        y :
            The target activity to compare against. Shape (n_time_bins, n_neurons).

        Returns
        -------
        :
            The negative log-likehood. Shape (1,).
        """
        pass

    @abc.abstractmethod
    def sample_generator(
        self, key: KeyArray, predicted_rate: jnp.ndarray
    ) -> jnp.ndarray:
        """
        Sample from the estimated distribution.

        This method generates random numbers from the desired distribution based on the given
        `predicted_rate`.

        Parameters
        ----------
        key :
            Random key used for the generation of random numbers in JAX.
        predicted_rate :
            Expected rate of the distribution. Shape (n_time_bins, n_neurons).

        Returns
        -------
        :
            Random numbers generated from the noise model with `predicted_rate`.
        """
        pass

    @abc.abstractmethod
    def residual_deviance(self, predicted_rate: jnp.ndarray, spike_counts: jnp.ndarray):
        r"""Compute the residual deviance for the noise model.

        Parameters
        ----------
        predicted_rate:
            The predicted firing rates. Shape (n_time_bins, n_neurons).
        spike_counts:
            The spike counts. Shape (n_time_bins, n_neurons).

        Returns
        -------
        :
            The residual deviance of the model.
        """
        pass

    @abc.abstractmethod
    def estimate_scale(self, predicted_rate: jnp.ndarray) -> None:
        r"""Estimate the scale parameter for the model.

        This method estimates the scale parameter, often denoted as $\phi$, which determines the dispersion
        of an exponential family distribution. The probability density function (pdf) for such a distribution
        is generally expressed as
        $f(x; \theta, \phi) \propto \exp \left(a(\phi)\left(  y\theta - \mathcal{k}(\theta) \right)\right)$.

        The relationship between variance and the scale parameter is given by:
        $$
        \text{var}(Y) = \frac{V(\mu)}{a(\phi)}.
        $$

        The scale parameter, $\phi$, is necessary for capturing the variance of the data accurately.

        Parameters
        ----------
        predicted_rate :
            The predicted rate values.
        """
        pass

    def pseudo_r2(self, predicted_rate: jnp.ndarray, y: jnp.ndarray):
        r"""Pseudo-$R^2$ calculation for a GLM.

        Compute the pseudo-$R^2$ metric as defined by Cohen et al. (2002)[$^1$](#--references).

        This metric evaluates the goodness-of-fit of the model relative to a null (baseline) model that assumes a
        constant mean for the observations. While the pseudo-$R^2$ is bounded between 0 and 1 for the training set,
        it can yield negative values on out-of-sample data, indicating potential overfitting.

        Parameters
        ----------
        predicted_rate:
            The mean neural activity. Expected shape: (n_time_bins, n_neurons)
        y:
            The neural activity. Expected shape: (n_time_bins, n_neurons)

        Returns
        -------
        :
            The pseudo-$R^2$ of the model. A value closer to 1 indicates a better model fit,
            whereas a value closer to 0 suggests that the model doesn't improve much over the null model.

        Notes
        -----
        The pseudo-$R^2$ score is calculated as follows,

        $$
        \begin{aligned}
        R_{\text{pseudo}}^2 &= \frac{LL(\bm{y}| \bm{\hat{\mu}}) - LL(\bm{y}|  \bm{\mu_0})}{LL(\bm{y}| \bm{y}) -
        LL(\bm{y}|  \bm{\mu_0})}\\
        &= \frac{D(\bm{y}; \bm{\mu_0}) - D(\bm{y}; \bm{\hat{\mu}})}{D(\bm{y}; \bm{\mu_0})},
        \end{aligned}
        $$

        where $\bm{y}=[y_1,\dots, y_T]$, $\bm{\hat{\mu}} = \left[\hat{\mu}_1, \dots, \hat{\mu}_T \right]$ and,
        $\bm{\mu_0} = \left[\mu_0, \dots, \mu_0 \right]$ are the counts, the model predicted rate and the average
        firing rates respectively, $LL$ is the log-likelihood averaged over the samples, and
        $D(\cdot\; ;\cdot)$ is the deviance averaged over samples,
        $$
        D(\bm{y}; \bm{\mu}) = 2 \left( LL(\bm{y}| \bm{y}) - LL(\bm{y}| \bm{\mu}) \right).
        $$

        References
        ----------
        1. Jacob Cohen, Patricia Cohen, Steven G. West, Leona S. Aiken.
        *Applied Multiple Regression/Correlation Analysis for the Behavioral Sciences*.
        3rd edition. Routledge, 2002. p.502. ISBN 978-0-8058-2223-6. (May 2012)
        """
        res_dev_t = self.residual_deviance(predicted_rate, y)
        resid_deviance = jnp.sum(res_dev_t**2)

        null_mu = jnp.ones(y.shape, dtype=jnp.float32) * y.mean()
        null_dev_t = self.residual_deviance(null_mu, y)
        null_deviance = jnp.sum(null_dev_t**2)

        return (null_deviance - resid_deviance) / null_deviance


class PoissonNoiseModel(NoiseModel):
    """
    Poisson Noise Model class for spike count data.

    The PoissonNoiseModel is designed to model the observed spike counts based on a Poisson distribution
    with a given rate. It provides methods for computing the negative log-likelihood, emission probability,
    and residual deviance for the given spike count data.

    Attributes
    ----------
    inverse_link_function :
        A function that maps the predicted rate to the domain of the Poisson parameter. Defaults to jnp.exp.

    See Also
    --------
    [NoiseModel](./#neurostatslib.noise_model.NoiseModel) : Base class for noise models.
    """

    def __init__(self, inverse_link_function=jnp.exp):
        super().__init__(inverse_link_function=inverse_link_function)
        self.scale = 1

    def negative_log_likelihood(
        self,
        predicted_rate: jnp.ndarray,
        y: jnp.ndarray,
    ) -> jnp.ndarray:
        r"""Compute the Poisson negative log-likelihood.

        This computes the Poisson negative log-likelihood of the predicted rates
        for the observed spike counts up to a constant.

        Parameters
        ----------
        predicted_rate :
            The predicted rate of the current model. Shape (n_time_bins, n_neurons).
        y :
            The target spikes to compare against. Shape (n_time_bins, n_neurons).

        Returns
        -------
        :
            The Poisson negative log-likehood. Shape (1,).

        Notes
        -----

        The formula for the Poisson mean log-likelihood is the following,

        $$
        \begin{aligned}
        \text{LL}(\hat{\lambda} | y) &= \frac{1}{T \cdot N} \sum_{n=1}^{N} \sum_{t=1}^{T}
        [y\_{tn} \log(\hat{\lambda}\_{tn}) - \hat{\lambda}\_{tn} - \log({y\_{tn}!})] \\\
        &= \frac{1}{T \cdot N} \sum_{n=1}^{N} \sum_{t=1}^{T} [y\_{tn} \log(\hat{\lambda}\_{tn}) -
        \hat{\lambda}\_{tn} - \Gamma({y\_{tn}+1})] \\\
        &= \frac{1}{T \cdot N} \sum_{n=1}^{N} \sum_{t=1}^{T} [y\_{tn} \log(\hat{\lambda}\_{tn}) -
        \hat{\lambda}\_{tn}] + \\text{const}
        \end{aligned}
        $$

        Because $\Gamma(k+1)=k!$, see [wikipedia](https://en.wikipedia.org/wiki/Gamma_function) for explanation.

        The $\log({y\_{tn}!})$ term is not a function of the parameters and can be disregarded
        when computing the loss-function. This is why we incorporated it into the `const` term.
        """
        predicted_rate = jnp.clip(predicted_rate, a_min=self.FLOAT_EPS)
        x = y * jnp.log(predicted_rate)
        # see above for derivation of this.
        return jnp.mean(predicted_rate - x)

    def sample_generator(
        self, key: KeyArray, predicted_rate: jnp.ndarray
    ) -> jnp.ndarray:
        """
        Sample from the Poisson distribution.

        This method generates random numbers from a Poisson distribution based on the given
        `predicted_rate`.

        Parameters
        ----------
        key :
            Random key used for the generation of random numbers in JAX.
        predicted_rate :
            Expected rate (lambda) of the Poisson distribution. Shape (n_time_bins, n_neurons).

        Returns
        -------
        jnp.ndarray
            Random numbers generated from the Poisson distribution based on the `predicted_rate`.
        """
        return jax.random.poisson(key, predicted_rate)

    def residual_deviance(
        self, predicted_rate: jnp.ndarray, spike_counts: jnp.ndarray
    ) -> jnp.ndarray:
        r"""Compute the residual deviance for a Poisson model.

        Parameters
        ----------
        predicted_rate:
            The predicted firing rates. Shape (n_time_bins, n_neurons).
        spike_counts:
            The spike counts. Shape (n_time_bins, n_neurons).

        Returns
        -------
        :
            The residual deviance of the model.

        Notes
        -----
        The deviance is a measure of the goodness of fit of a statistical model.
        For a Poisson model, the residual deviance is computed as:

        $$
        \begin{aligned}
            D(y\_{tn}, \hat{y}\_{tn}) &= 2 \left[ y\_{tn} \log\left(\frac{y\_{tn}}{\hat{y}\_{tn}}\right)
            - (y\_{tn} - \hat{y}\_{tn}) \right]\\\
            &= 2 \left( \text{LL}\left(y\_{tn} | y\_{tn}\right) - \text{LL}\left(y\_{tn} | \hat{y}\_{tn}\right)\right)
        \end{aligned}
        $$

        where $ y $ is the observed data, $ \hat{y} $ is the predicted data, and $\text{LL}$ is the model
        log-likelihood. Lower values of deviance indicate a better fit.
        """
        # this takes care of 0s in the log
        ratio = jnp.clip(spike_counts / predicted_rate, self.FLOAT_EPS, jnp.inf)
        resid_dev = 2 * (
            spike_counts * jnp.log(ratio) - (spike_counts - predicted_rate)
        )
        return resid_dev

    def estimate_scale(self, predicted_rate: jnp.ndarray) -> None:
        r"""
        Assign 1 to the scale parameter of the Poisson model.

        For the Poisson exponential family distribution, the scale parameter $\phi$ is always 1.
        This property is consistent with the fact that the variance equals the mean in a Poisson distribution.
        As given in the general exponential family expression:
        $$
        \text{var}(Y) = \frac{V(\mu)}{a(\phi)},
        $$
        for the Poisson family, it simplifies to $\text{var}(Y) = \mu$ since $a(\phi) = 1$ and $V(\mu) = \mu$.

        Parameters
        ----------
        predicted_rate :
            The predicted rate values. This is not used in the Poisson model for estimating scale,
            but is retained for compatibility with the abstract method signature.
        """
        self.scale = 1.0
