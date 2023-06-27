import pytest
import neurostatslib.basis as basis
import utils_testing
import numpy as np

from numpy.typing import NDArray
# automatic define user accessible basis and check the methods



def test_basis_abstract_method_compliance() -> None:
    """
    Check that each non-abstract class implements all abstract methods of super-classes.

    Raises
    ------
    ValueError
        If any of the non-abstract classes doesn't re-implement at least one of the abstract methods it inherits.
    """
    utils_testing.check_all_abstract_methods_compliance(basis)
    return


def test_init_and_evaluate_basis(initialize_basis: dict, capfd) -> None:
    """
    Test initialization and evaluation of basis classes.

    Parameters:
    -----------
    - initialize_basis:
        A dictionary containing basis names as keys and their initialization arguments as values.
    - capfd
        pytest fixture for capturing stdout and stderr.

    Raises:
    -------
    - ValueError
        If the dimensions of the evaluated basis do not match the expected dimensions.

    Returns:
    - None
    """
    for basis_name in initialize_basis:
        basis_class = getattr(basis, basis_name)
        with capfd.disabled():
            disp_str = f"Testing class {basis_name}\n"
            disp_str += '-' * (len(disp_str) - 1)
            print(disp_str)
        for args in initialize_basis[basis_name]:
            basis_instance = basis_class(*args)
            with capfd.disabled():
                print(f"num basis: {args[0]}")
            for window_size in [50, 80, 100]:
                eval_basis = basis_instance.evaluate(np.linspace(0, 1, window_size))
                capfd.readouterr()
                if eval_basis.shape[0] != args[0]:
                    raise ValueError(f"Dimensions do not agree: The number of basis should match the first dimensiton of the evaluated basis."
                                     f"The number of basis is {args[0]}",
                                     f"The first dimension of the evaluated basis is {eval_basis.shape[0]}")

                if eval_basis.shape[1] != window_size:
                    raise ValueError(
                        f"Dimensions do not agree: The window size should match the second dimensiton of the evaluated basis."
                        f"The window size is {window_size}",
                        f"The second dimension of the evaluated basis is {eval_basis.shape[1]}")


class TestBspline:
    # a map specifying multiple argument sets for a test method, this parameters should raise an exception
    params = {'test_msplinebasis_insufficient_nbasis': []}

    # fill the parameter grid for M-spline so that it fails due to the number of basis
    for n_basis in [-1, 0]:
        for order in [2]:
            params['test_msplinebasis_insufficient_nbasis'].append({'n_basis': n_basis, 'order': order})

    params['test_basis_eval_checks'] = [
        {'basis_obj': basis.MSplineBasis(10)}
        , basis.RaisedCosineBasisLog(10),basis.RaisedCosineBasisLinear(10),basis.OrthExponentialBasis(10, np.linspace(1,10,10))}
    ]
    def test_msplinebasis_insufficient_nbasis(self, n_basis, order):
        with pytest.raises(ValueError):
            basis.MSplineBasis(n_basis, order)

    def test_basis_eval_checks(self, n_basis, order):
        with pytest.raises(ValueError):
            basis.MSplineBasis(n_basis, order)

