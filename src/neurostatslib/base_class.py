"""Abstract class for models.

Inheriting this class will result in compatibility with sci-kit learn pipelines.
"""

import abc
import inspect
import warnings
from collections import defaultdict
from typing import Tuple, Union, Optional, Literal, Callable, Sequence

import jax
import jax.numpy as jnp
from numpy.typing import NDArray, ArrayLike, DTypeLike


class _Base(abc.ABC):
    def __init__(self, **kwargs):
        self._kwargs_keys = list(kwargs.keys())
        for key in kwargs:
            setattr(self, key, kwargs[key])

    def get_params(self, deep=True):
        """
        from scikit-learn, get parameters by inspecting init
        Parameters
        ----------
        deep

        Returns
        -------

        """
        out = dict()
        for key in self._get_param_names():
            value = getattr(self, key)
            if deep and hasattr(value, "get_params") and not isinstance(value, type):
                deep_items = value.get_params().items()
                out.update((key + "__" + k, val) for k, val in deep_items)
            out[key] = value
        # add kwargs
        for key in self._kwargs_keys:
            out[key] = getattr(self, key)
        return out

    def set_params(self, **params):
        """Set the parameters of this estimator.

        The method works on simple estimators as well as on nested objects
        (such as :class:`~sklearn.pipeline.Pipeline`). The latter have
        parameters of the form ``<component>__<parameter>`` so that it's
        possible to update each component of a nested object.

        Parameters
        ----------
        **params : dict
            Estimator parameters.

        Returns
        -------
        self : estimator instance
            Estimator instance.
        """
        if not params:
            # Simple optimization to gain speed (inspect is slow)
            return self
        valid_params = self.get_params(deep=True)
        nested_params = defaultdict(dict)  # grouped by prefix
        for key, value in params.items():
            key, delim, sub_key = key.partition("__")
            if key not in valid_params:
                local_valid_params = self._get_param_names()
                raise ValueError(
                    f"Invalid parameter {key!r} for estimator {self}. "
                    f"Valid parameters are: {local_valid_params!r}."
                )

            if delim:
                nested_params[key][sub_key] = value
            else:
                setattr(self, key, value)
                valid_params[key] = value

        for key, sub_params in nested_params.items():
            # TODO(1.4): remove specific handling of "base_estimator".
            # The "base_estimator" key is special. It was deprecated and
            # renamed to "estimator" for several estimators. This means we
            # need to translate it here and set sub-parameters on "estimator",
            # but only if the user did not explicitly set a value for
            # "base_estimator".
            if (
                key == "base_estimator"
                and valid_params[key] == "deprecated"
                and self.__module__.startswith("sklearn.")
            ):
                warnings.warn(
                    (
                        f"Parameter 'base_estimator' of {self.__class__.__name__} is"
                        " deprecated in favor of 'estimator'. See"
                        f" {self.__class__.__name__}'s docstring for more details."
                    ),
                    FutureWarning,
                    stacklevel=2,
                )
                key = "estimator"
            valid_params[key].set_params(**sub_params)

        return self

    @classmethod
    def _get_param_names(cls):
        """Get parameter names for the estimator"""
        # fetch the constructor or the original constructor before
        # deprecation wrapping if any
        init = getattr(cls.__init__, "deprecated_original", cls.__init__)
        if init is object.__init__:
            # No explicit constructor to introspect
            return []

        # introspect the constructor arguments to find the model parameters
        # to represent
        init_signature = inspect.signature(init)
        # Consider the constructor parameters excluding 'self'
        parameters = [
            p
            for p in init_signature.parameters.values()
            if p.name != "self" and p.kind != p.VAR_KEYWORD
        ]
        for p in parameters:
            if p.kind == p.VAR_POSITIONAL:
                raise RuntimeError(
                    "GLM estimators should always "
                    "specify their parameters in the signature"
                    " of their __init__ (no varargs)."
                    " %s with constructor %s doesn't "
                    " follow this convention." % (cls, init_signature)
                )

        # Consider the constructor parameters excluding 'self'
        parameters = [
            p.name
            for p in init_signature.parameters.values()
            if p.name != "self"
        ]

        # remove kwargs
        if 'kwargs' in parameters:
            parameters.remove('kwargs')
        # Extract and sort argument names excluding 'self'
        return sorted(parameters)


class BaseRegressor(_Base, abc.ABC):
    FLOAT_EPS = jnp.finfo(jnp.float32).eps

    @abc.abstractmethod
    def fit(self, X: Union[NDArray, jnp.ndarray], y: Union[NDArray, jnp.ndarray]):
        pass

    @abc.abstractmethod
    def predict(self, X: Union[NDArray, jnp.ndarray]) -> jnp.ndarray:
        pass

    @abc.abstractmethod
    def score(
        self, X: Union[NDArray, jnp.ndarray], y: Union[NDArray, jnp.ndarray]
    ) -> jnp.ndarray:
        pass

    @abc.abstractmethod
    def simulate(
            self,
            random_key: jax.random.PRNGKeyArray,
            n_timesteps: int,
            init_spikes: Union[NDArray, jnp.ndarray],
            coupling_basis_matrix: Union[NDArray, jnp.ndarray],
            feedforward_input: Optional[Union[NDArray, jnp.ndarray]] = None,
            device: Literal["cpu", "gpu", "tpu"] = "cpu"
    ):
        pass

    @staticmethod
    def _convert_to_jnp_ndarray(
        *args: Union[NDArray, jnp.ndarray], data_type: jnp.dtype = jnp.float32
    ) -> Tuple[jnp.ndarray, ...]:
        return tuple(jnp.asarray(arg, dtype=data_type) for arg in args)

    @staticmethod
    def _has_invalid_entry(array: jnp.ndarray) -> bool:
        """Check if the array has nans or infs.

        Parameters
        ----------
        array:
            The array to be checked.

        Returns
        -------
            True if a nan or an inf is present, False otherwise

        """
        return (jnp.isinf(array) | jnp.isnan(array)).any()

    @staticmethod
    def _check_and_convert_params(params: ArrayLike) -> Tuple[jnp.ndarray, ...]:
        """
        Validate the dimensions and consistency of parameters and data.

        This function checks the consistency of shapes and dimensions for model
        parameters.
        It ensures that the parameters and data are compatible for the model.

        """
        if not hasattr(params, "__getitem__"):
            raise TypeError("Initial parameters must be array-like!")
        try:
            params = tuple(jnp.asarray(par, dtype=jnp.float32) for par in params)
        except ValueError:
            raise TypeError(
                "Initial parameters must be array-like of array-like objects"
                "with numeric data-type!"
            )

        if len(params) != 2:
            raise ValueError("Params needs to be array-like of length two.")

        if params[0].ndim != 2:
            raise ValueError(
                "params[0] term must be of shape (n_neurons, n_features), but"
                f"params[0] has {params[0].ndim} dimensions!"
            )
        if params[1].ndim != 1:
            raise ValueError(
                "params[1] term must be of shape (n_neurons,) but "
                f"params[1] has {params[1].ndim} dimensions!"
            )
        return params

    @staticmethod
    def _check_input_dimensionality(
            X: Optional[jnp.ndarray] = None, y: Optional[jnp.ndarray] = None
    ):
        if not (y is None):
            if y.ndim != 2:
                raise ValueError(
                    "y must be two-dimensional, with shape (n_timebins, n_neurons)"
                )
        if not (X is None):
            if X.ndim != 3:
                raise ValueError(
                    "X must be three-dimensional, with shape (n_timebins, n_neurons, n_features)"
                )

    @staticmethod
    def _check_input_and_params_consistency(
            params: Tuple[jnp.ndarray, jnp.ndarray],
            X: Optional[jnp.ndarray] = None,
            y: Optional[jnp.ndarray] = None,
    ):
        """
        Validate the number of neurons in model parameters and input arguments.

        Raises:
        ------
            ValueError
                - if the number of neurons is consistent across the model parameters (`params`) and
                any additional inputs (`X` or `y` when provided).
                - if the number of features is inconsistent between params[1] and X (when provided).

        """
        n_neurons = params[0].shape[0]
        if n_neurons != params[1].shape[0]:
            raise ValueError(
                "Model parameters have inconsistent shapes. "
                "Spike basis coefficients must be of shape (n_neurons, n_features), and "
                "bias terms must be of shape (n_neurons,) but n_neurons doesn't look the same in both! "
                f"Coefficients n_neurons: {params[0].shape[0]}, bias n_neurons: {params[1].shape[0]}"
            )

        if y is not None:
            if y.shape[1] != n_neurons:
                raise ValueError(
                    "The number of neuron in the model parameters and in the inputs"
                    "must match."
                    f"parameters has n_neurons: {n_neurons}, "
                    f"the input provided has n_neurons: {y.shape[1]}"
                )

        if X is not None:
            if X.shape[1] != n_neurons:
                raise ValueError(
                    "The number of neuron in the model parameters and in the inputs"
                    "must match."
                    f"parameters has n_neurons: {n_neurons}, "
                    f"the input provided has n_neurons: {X.shape[1]}"
                )
            if params[0].shape[1] != X.shape[2]:
                raise ValueError(
                    "Inconsistent number of features. "
                    f"spike basis coefficients has {params[0].shape[1]} features, "
                    f"X has {X.shape[2]} features instead!"
                )

    @staticmethod
    def _check_input_n_timepoints(X: jnp.ndarray, y: jnp.ndarray):
        if X.shape[0] != y.shape[0]:
            raise ValueError(
                "The number of time-points in X and y must agree. "
                f"X has {X.shape[0]} time-points, "
                f"y has {y.shape[0]} instead!"
            )

    def _preprocess_fit(
            self,
            X: Union[NDArray, jnp.ndarray],
            y: Union[NDArray, jnp.ndarray],
            init_params: Optional[Tuple[ArrayLike, ArrayLike]] = None
    ) -> Tuple[jnp.ndarray, jnp.ndarray, Tuple[jnp.ndarray, jnp.ndarray]]:

        # check input dimensionality
        self._check_input_dimensionality(X, y)
        self._check_input_n_timepoints(X, y)

        # convert to jnp.ndarray of floats
        X, y = self._convert_to_jnp_ndarray(
            X, y, data_type=jnp.float32
        )

        if self._has_invalid_entry(X):
            raise ValueError("Input X contains a NaNs or Infs!")
        elif self._has_invalid_entry(y):
            raise ValueError("Input y contains a NaNs or Infs!")

        _, n_neurons = y.shape
        n_features = X.shape[2]

        # Initialize parameters
        if init_params is None:
            # Ws, spike basis coeffs
            init_params = (
                jnp.zeros((n_neurons, n_features)),
                # bs, bias terms
                jnp.log(jnp.mean(y, axis=0)),
            )
        else:
            # check parameter length, shape and dimensionality, convert to jnp.ndarray.
            init_params = self._check_and_convert_params(init_params)

        # check that the inputs and the parameters has consistent sizes
        self._check_input_and_params_consistency(init_params, X, y)

        return X, y, init_params