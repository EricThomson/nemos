"""Abstract class for estimators."""

import abc
import inspect
import warnings
from collections import defaultdict
from typing import Any, Optional, Tuple, Union

import jax
import jax.numpy as jnp
from numpy.typing import ArrayLike, NDArray

from .utils import check_invalid_entry


class Base:
    """Base class for nemos estimators.

    A base class for estimators with utilities for getting and setting parameters,
    and for interacting with specific devices like CPU, GPU, and TPU.

    This class provides utilities for:
    - Getting and setting parameters using introspection.
    - Sending arrays to target devices (CPU, GPU, TPU).

    Parameters
    ----------
    **kwargs : dict
        Arbitrary keyword arguments.

    Notes
    -----
    The class provides helper methods mimicking scikit-learn's get_params and set_params.
    Additionally, it has methods for selecting target devices and sending arrays to them.
    """

    def get_params(self, deep=True):
        """
        From scikit-learn, get parameters by inspecting init.

        Parameters
        ----------
        deep

        Returns
        -------
            out:
                A dictionary containing the parameters. Key is the parameter
                name, value is the parameter value.
        """
        out = dict()
        for key in self._get_param_names():
            value = getattr(self, key)
            if deep and hasattr(value, "get_params") and not isinstance(value, type):
                deep_items = value.get_params().items()
                out.update((key + "__" + k, val) for k, val in deep_items)
            out[key] = value
        return out

    def set_params(self, **params: Any):
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
        nested_params: defaultdict = defaultdict(dict)  # grouped by prefix
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
        """Get parameter names for the estimator."""
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
            p.name for p in init_signature.parameters.values() if p.name != "self"
        ]

        # remove kwargs
        if "kwargs" in parameters:
            parameters.remove("kwargs")
        # Extract and sort argument names excluding 'self'
        return sorted(parameters)


class BaseRegressor(Base, abc.ABC):
    """Abstract base class for GLM regression models.

    This class encapsulates the common functionality for Generalized Linear Models (GLM)
    regression models. It provides an abstraction for fitting the model, making predictions,
    scoring the model, simulating responses, and preprocessing data. Concrete classes
    are expected to provide specific implementations of the abstract methods defined here.

    See Also
    --------
    Concrete models:

    - [`GLM`](../glm/#nemos.glm.GLM): A feed-forward GLM implementation.
    - [`GLMRecurrent`](../glm/#nemos.glm.GLMRecurrent): A recurrent GLM implementation.
    """

    @abc.abstractmethod
    def fit(self, X: Union[NDArray, jnp.ndarray], y: Union[NDArray, jnp.ndarray]):
        """Fit the model to neural activity."""
        pass

    @abc.abstractmethod
    def predict(self, X: Union[NDArray, jnp.ndarray]) -> jnp.ndarray:
        """Predict rates based on fit parameters."""
        pass

    @abc.abstractmethod
    def score(
        self,
        X: Union[NDArray, jnp.ndarray],
        y: Union[NDArray, jnp.ndarray],
        # may include score_type or other additional model dependent kwargs
        **kwargs,
    ) -> jnp.ndarray:
        """Score the predicted firing rates (based on fit) to the target neural activity."""
        pass

    @abc.abstractmethod
    def simulate(
        self,
        random_key: jax.random.PRNGKeyArray,
        feed_forward_input: Union[NDArray, jnp.ndarray],
    ):
        """Simulate neural activity in response to a feed-forward input and recurrent activity."""
        pass

    @staticmethod
    def _check_and_convert_params(
        params: Tuple[ArrayLike, ArrayLike], data_type: Optional[jnp.dtype] = None
    ) -> Tuple[jnp.ndarray, jnp.ndarray]:
        """
        Validate the dimensions and consistency of parameters and data.

        This function checks the consistency of shapes and dimensions for model
        parameters.
        It ensures that the parameters and data are compatible for the model.

        """
        try:
            params = tuple(jnp.asarray(par, dtype=data_type) for par in params)
        except (ValueError, TypeError):
            raise TypeError(
                "Initial parameters must be array-like of array-like objects "
                "with numeric data-type!"
            )

        if len(params) != 2:
            raise ValueError("Params needs to be array-like of length two.")

        if params[0].ndim != 2:
            raise ValueError(
                "params[0] must be of shape (n_neurons, n_features), but"
                f"params[0] has {params[0].ndim} dimensions!"
            )
        if params[1].ndim != 1:
            raise ValueError(
                "params[1] must be of shape (n_neurons,) but "
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

        Raises
        ------
            ValueError
                - if the number of neurons is inconsistent across the model parameters (`params`) and
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
                    "The number of neurons in the model parameters and in the inputs"
                    "must match."
                    f"parameters has n_neurons: {n_neurons}, "
                    f"the input provided has n_neurons: {y.shape[1]}"
                )

        if X is not None:
            if X.shape[1] != n_neurons:
                raise ValueError(
                    "The number of neurons in the model parameters and in the inputs"
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
        init_params: Optional[Tuple[ArrayLike, ArrayLike]] = None,
    ) -> Tuple[jnp.ndarray, jnp.ndarray, Tuple[jnp.ndarray, jnp.ndarray]]:
        """Preprocess input data and initial parameters for the fit method.

        This method carries out the following preprocessing steps:

        - Convert to jax.numpy.ndarray

        - Check the dimensionality of the inputs.

        - Check for any NaNs or Infs in the inputs.

        - If `init_params` is not provided, initialize it with default values.

        - Validate the consistency of input dimensions with the initial parameters.

        Parameters
        ----------
        X :
            Input data, expected to be of shape (n_timebins, n_neurons, n_features).
        y :
            Target values, expected to be of shape (n_timebins, n_neurons).
        init_params :
            Initial parameters for the model. If None, they are initialized with default values.

        Returns
        -------
        X :
            Preprocessed input data `X` converted to jnp.ndarray.
        y :
            Target values `y` converted to jnp.ndarray.
        init_param :
            Initialized parameters converted to jnp.ndarray.

        Raises
        ------
        ValueError
            If there are inconsistencies in the input shapes or if NaNs or Infs are detected.
        """
        X, y = jnp.asarray(X, dtype=float), jnp.asarray(y, dtype=float)

        # check input dimensionality
        self._check_input_dimensionality(X, y)
        self._check_input_n_timepoints(X, y)

        check_invalid_entry(X, "X")
        check_invalid_entry(y, "y")

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
        self._check_input_and_params_consistency(init_params, X=X, y=y)

        return X, y, init_params

    def _preprocess_simulate(
        self,
        feedforward_input: Union[NDArray, jnp.ndarray],
        params_feedforward: Tuple[jnp.ndarray, jnp.ndarray],
        init_y: Optional[Union[NDArray, jnp.ndarray]] = None,
        params_recurrent: Optional[Tuple[jnp.ndarray, jnp.ndarray]] = None,
    ) -> Tuple[jnp.ndarray, ...]:
        """
        Preprocess the input data and parameters for simulation.

        This method handles the conversion of the input data to `jnp.ndarray`, checks the
        input's dimensionality, and ensures the input's consistency with the provided parameters.
        It also verifies that the feedforward input does not have any invalid entries (NaNs or Infs).

        Parameters
        ----------
        feedforward_input :
            Input data for the feedforward process. Expected shape: (n_timesteps, n_neurons, n_basis_input).
        params_feedforward :
            Parameters corresponding to the feedforward input. Expected shape: (n_neurons, n_basis_input).
        init_y :
            Initial values for the feedback process. If provided, its dimensionality and consistency
            with params_r will be checked. Expected shape if provided: (window_size, n_neurons).
        params_recurrent :
            Parameters corresponding to the feedback input (init_y). Required if init_y is provided.
            Expected shape if provided: (window_size, n_basis_coupling)

        Returns
        -------
        :
            Preprocessed input data, optionally with the initial values for feedback if provided.

        Raises
        ------
        ValueError
            If the feedforward_input contains NaNs or Infs.
            If the dimensionality or consistency checks fail for the provided data and parameters.
        """
        feedforward_input = jnp.asarray(feedforward_input, dtype=float)
        self._check_input_dimensionality(X=feedforward_input)
        self._check_input_and_params_consistency(
            params_feedforward, X=feedforward_input
        )

        check_invalid_entry(feedforward_input, "feedforward_input")

        # Ensure that both or neither of `init_y` and `params_r` are provided
        if (init_y is None) != (params_recurrent is None):
            raise ValueError(
                "Both `init_y` and `params_r` should be provided, or neither should be provided."
            )
        # If both are provided, perform checks and conversions
        elif init_y is not None and params_recurrent is not None:
            init_y = jnp.asarray(init_y, dtype=float)
            self._check_input_dimensionality(y=init_y)
            self._check_input_and_params_consistency(params_recurrent, y=init_y)
            return feedforward_input, init_y

        return (feedforward_input,)