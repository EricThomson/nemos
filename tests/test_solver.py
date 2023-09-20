import jax
import jax.numpy as jnp
import numpy as np
import pytest
import statsmodels.api as sm
from sklearn.linear_model import PoissonRegressor

import neurostatslib as nsl


class TestSolver:
    cls = nsl.solver.Solver
    def test_abstract_nature_of_solver(self):
        """Test that Solver can't be instantiated."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class Solver"):
            self.cls("GradientDescent")


class TestUnRegularizedSolver:
    cls = nsl.solver.UnRegularizedSolver

    @pytest.mark.parametrize("solver_name", ["GradientDescent", "BFGS", "ProximalGradient", "AGradientDescent", 1])
    def test_init_solver_name(self, solver_name):
        """Test UnRegularizedSolver acceptable solvers."""
        acceptable_solvers = [
            "GradientDescent",
            "BFGS",
            "LBFGS",
            "ScipyMinimize",
            "NonlinearCG",
            "ScipyBoundedMinimize",
            "LBFGSB"
        ]
        raise_exception = solver_name not in acceptable_solvers
        if raise_exception:
            with pytest.raises(ValueError, match=f"Solver `{solver_name}` not allowed for "):
                self.cls(solver_name)
        else:
            self.cls(solver_name)

    @pytest.mark.parametrize("solver_name", ["GradientDescent", "BFGS", "ProximalGradient", "AGradientDescent", 1])
    def test_set_solver_name_allowed(self, solver_name):
        """Test UnRegularizedSolver acceptable solvers."""
        acceptable_solvers = [
            "GradientDescent",
            "BFGS",
            "LBFGS",
            "ScipyMinimize",
            "NonlinearCG",
            "ScipyBoundedMinimize",
            "LBFGSB"
        ]
        solver = self.cls("GradientDescent")
        raise_exception = solver_name not in acceptable_solvers
        if raise_exception:
            with pytest.raises(ValueError, match=f"Solver `{solver_name}` not allowed for "):
                solver.set_params(solver_name=solver_name)
        else:
            solver.set_params(solver_name=solver_name)

    @pytest.mark.parametrize("solver_name", ["GradientDescent", "BFGS"])
    @pytest.mark.parametrize("solver_kwargs", [{"tol": 10**-10}, {"tols": 10**-10}])
    def test_init_solver_kwargs(self, solver_name, solver_kwargs):
        """Test RidgeSolver acceptable kwargs."""

        raise_exception = "tols" in list(solver_kwargs.keys())
        if raise_exception:
            with pytest.raises(NameError, match="kwargs {'tols'} in solver_kwargs not a kwarg"):
                self.cls(solver_name, solver_kwargs=solver_kwargs)
        else:
            self.cls(solver_name, solver_kwargs=solver_kwargs)

    @pytest.mark.parametrize("loss", [jnp.exp, 1, None, {}])
    def test_loss_is_callable(self, loss):
        """Test that the loss function is a callable"""
        raise_exception = not callable(loss)
        if raise_exception:
            with pytest.raises(TypeError, match="The loss function must a Callable"):
                self.cls("GradientDescent").instantiate_solver(loss)
        else:
            self.cls("GradientDescent").instantiate_solver(loss)

    @pytest.mark.parametrize("loss", [jnp.exp, np.exp, nsl.glm.GLM()._score])
    def test_loss_type_jax_or_glm(self, loss):
        """Test that the loss function is a callable"""
        raise_exception = (not hasattr(loss, "__module__")) or \
                          (not (loss.__module__.startswith("jax.") or
                                loss.__module__.startswith("neurostatslib.glm")))
        if raise_exception:
            with pytest.raises(ValueError, match=f"The function {loss.__name__} is not from the jax namespace."):
                self.cls("GradientDescent").instantiate_solver(loss)
        else:
            self.cls("GradientDescent").instantiate_solver(loss)

    @pytest.mark.parametrize("solver_name", ["GradientDescent", "BFGS"])
    def test_run_solver(self, solver_name, poissonGLM_model_instantiation):
        """Test that the solver runs."""

        X, y, model, true_params, firing_rate = poissonGLM_model_instantiation
        runner = self.cls("GradientDescent").instantiate_solver(model._score)
        runner((true_params[0]*0., true_params[1]), X, y)

    def test_solver_output_match(self, poissonGLM_model_instantiation):
        """Test that different solvers converge to the same solution."""
        jax.config.update("jax_enable_x64", True)
        X, y, model, true_params, firing_rate = poissonGLM_model_instantiation
        # set precision to float64 for accurate matching of the results
        model.data_type = jnp.float64
        runner_gd = self.cls("GradientDescent", {"tol": 10**-12}).instantiate_solver(model._score)
        runner_bfgs = self.cls("BFGS", {"tol": 10**-12}).instantiate_solver(model._score)
        runner_scipy = self.cls("ScipyMinimize", {"method": "BFGS", "tol": 10**-12}).instantiate_solver(model._score)
        weights_gd, intercepts_gd = runner_gd((true_params[0] * 0., true_params[1]), X, y)[0]
        weights_bfgs, intercepts_bfgs = runner_bfgs((true_params[0] * 0., true_params[1]), X, y)[0]
        weights_scipy, intercepts_scipy = runner_scipy((true_params[0] * 0., true_params[1]), X, y)[0]

        match_weights = np.allclose(weights_gd, weights_bfgs) and \
                        np.allclose(weights_gd, weights_scipy)
        match_intercepts = np.allclose(intercepts_gd, intercepts_bfgs) and \
                           np.allclose(intercepts_gd, intercepts_scipy)
        if (not match_weights) or (not match_intercepts):
            raise ValueError("Convex estimators should converge to the same numerical value.")

    def test_solver_match_sklearn(self, poissonGLM_model_instantiation):
        """Test that different solvers converge to the same solution."""
        jax.config.update("jax_enable_x64", True)
        X, y, model, true_params, firing_rate = poissonGLM_model_instantiation
        # set precision to float64 for accurate matching of the results
        model.data_type = jnp.float64
        solver = self.cls("GradientDescent", {"tol": 10**-12})
        runner_bfgs = solver.instantiate_solver(model._score)
        weights_bfgs, intercepts_bfgs = runner_bfgs((true_params[0] * 0., true_params[1]), X, y)[0]
        model_skl = PoissonRegressor(fit_intercept=True, tol=10**-12, alpha=0.)
        model_skl.fit(X[:,0], y[:, 0])

        match_weights = np.allclose(model_skl.coef_, weights_bfgs.flatten())
        match_intercepts = np.allclose(model_skl.intercept_, intercepts_bfgs.flatten())
        if (not match_weights) or (not match_intercepts):
            raise ValueError("Ridge GLM solver estimate does not match sklearn!")


class TestRidgeSolver:
    cls = nsl.solver.RidgeSolver

    @pytest.mark.parametrize("solver_name", ["GradientDescent", "BFGS", "ProximalGradient", "AGradientDescent", 1])
    def test_init_solver_name(self, solver_name):
        """Test RidgeSolver acceptable solvers."""
        acceptable_solvers = [
            "GradientDescent",
            "BFGS",
            "LBFGS",
            "ScipyMinimize",
            "NonlinearCG",
            "ScipyBoundedMinimize",
            "LBFGSB"
        ]
        raise_exception = solver_name not in acceptable_solvers
        if raise_exception:
            with pytest.raises(ValueError, match=f"Solver `{solver_name}` not allowed for "):
                self.cls(solver_name)
        else:
            self.cls(solver_name)

    @pytest.mark.parametrize("solver_name", ["GradientDescent", "BFGS", "ProximalGradient", "AGradientDescent", 1])
    def test_set_solver_name_allowed(self, solver_name):
        """Test RidgeSolver acceptable solvers."""
        acceptable_solvers = [
            "GradientDescent",
            "BFGS",
            "LBFGS",
            "ScipyMinimize",
            "NonlinearCG",
            "ScipyBoundedMinimize",
            "LBFGSB"
        ]
        solver = self.cls("GradientDescent")
        raise_exception = solver_name not in acceptable_solvers
        if raise_exception:
            with pytest.raises(ValueError, match=f"Solver `{solver_name}` not allowed for "):
                solver.set_params(solver_name=solver_name)
        else:
            solver.set_params(solver_name=solver_name)

    @pytest.mark.parametrize("solver_name", ["GradientDescent", "BFGS"])
    @pytest.mark.parametrize("solver_kwargs", [{"tol": 10**-10}, {"tols": 10**-10}])
    def test_init_solver_kwargs(self, solver_name, solver_kwargs):
        """Test RidgeSolver acceptable kwargs."""

        raise_exception = "tols" in list(solver_kwargs.keys())
        if raise_exception:
            with pytest.raises(NameError, match="kwargs {'tols'} in solver_kwargs not a kwarg"):
                self.cls(solver_name, solver_kwargs=solver_kwargs)
        else:
            self.cls(solver_name, solver_kwargs=solver_kwargs)

    @pytest.mark.parametrize("loss", [jnp.exp, 1, None, {}])
    def test_loss_is_callable(self, loss):
        """Test that the loss function is a callable"""
        raise_exception = not callable(loss)
        if raise_exception:
            with pytest.raises(TypeError, match="The loss function must a Callable"):
                self.cls("GradientDescent").instantiate_solver(loss)
        else:
            self.cls("GradientDescent").instantiate_solver(loss)

    @pytest.mark.parametrize("loss", [jnp.exp, np.exp, nsl.glm.GLM()._score])
    def test_loss_type_jax_or_glm(self, loss):
        """Test that the loss function is a callable"""
        raise_exception = (not hasattr(loss, "__module__")) or \
                          (not (loss.__module__.startswith("jax.") or
                                loss.__module__.startswith("neurostatslib.glm")))
        if raise_exception:
            with pytest.raises(ValueError, match=f"The function {loss.__name__} is not from the jax namespace."):
                self.cls("GradientDescent").instantiate_solver(loss)
        else:
            self.cls("GradientDescent").instantiate_solver(loss)

    @pytest.mark.parametrize("solver_name", ["GradientDescent", "BFGS"])
    def test_run_solver(self, solver_name, poissonGLM_model_instantiation):
        """Test that the solver runs."""

        X, y, model, true_params, firing_rate = poissonGLM_model_instantiation
        runner = self.cls("GradientDescent").instantiate_solver(model._score)
        runner((true_params[0]*0., true_params[1]), X, y)

    def test_solver_output_match(self, poissonGLM_model_instantiation):
        """Test that different solvers converge to the same solution."""
        jax.config.update("jax_enable_x64", True)
        X, y, model, true_params, firing_rate = poissonGLM_model_instantiation
        # set precision to float64 for accurate matching of the results
        model.data_type = jnp.float64
        runner_gd = self.cls("GradientDescent", {"tol": 10**-12}).instantiate_solver(model._score)
        runner_bfgs = self.cls("BFGS", {"tol": 10**-12}).instantiate_solver(model._score)
        runner_scipy = self.cls("ScipyMinimize", {"method": "BFGS", "tol": 10**-12}).instantiate_solver(model._score)
        weights_gd, intercepts_gd = runner_gd((true_params[0] * 0., true_params[1]), X, y)[0]
        weights_bfgs, intercepts_bfgs = runner_bfgs((true_params[0] * 0., true_params[1]), X, y)[0]
        weights_scipy, intercepts_scipy = runner_scipy((true_params[0] * 0., true_params[1]), X, y)[0]

        match_weights = np.allclose(weights_gd, weights_bfgs) and \
                        np.allclose(weights_gd, weights_scipy)
        match_intercepts = np.allclose(intercepts_gd, intercepts_bfgs) and \
                           np.allclose(intercepts_gd, intercepts_scipy)
        if (not match_weights) or (not match_intercepts):
            raise ValueError("Convex estimators should converge to the same numerical value.")

    def test_solver_match_sklearn(self, poissonGLM_model_instantiation):
        """Test that different solvers converge to the same solution."""
        jax.config.update("jax_enable_x64", True)
        X, y, model, true_params, firing_rate = poissonGLM_model_instantiation
        # set precision to float64 for accurate matching of the results
        model.data_type = jnp.float64
        solver = self.cls("GradientDescent", {"tol": 10**-12})
        runner_bfgs = solver.instantiate_solver(model._score)
        weights_bfgs, intercepts_bfgs = runner_bfgs((true_params[0] * 0., true_params[1]), X, y)[0]
        model_skl = PoissonRegressor(fit_intercept=True, tol=10**-12, alpha=solver.regularizer_strength)
        model_skl.fit(X[:,0], y[:, 0])

        match_weights = np.allclose(model_skl.coef_, weights_bfgs.flatten())
        match_intercepts = np.allclose(model_skl.intercept_, intercepts_bfgs.flatten())
        if (not match_weights) or (not match_intercepts):
            raise ValueError("Ridge GLM solver estimate does not match sklearn!")


class TestLassoSolver:
    cls = nsl.solver.LassoSolver

    @pytest.mark.parametrize("solver_name", ["GradientDescent", "BFGS", "ProximalGradient", "AGradientDescent", 1])
    def test_init_solver_name(self, solver_name):
        """Test LassoSolver acceptable solvers."""
        acceptable_solvers = [
            "ProximalGradient"
        ]
        raise_exception = solver_name not in acceptable_solvers
        if raise_exception:
            with pytest.raises(ValueError, match=f"Solver `{solver_name}` not allowed for "):
                self.cls(solver_name)
        else:
            self.cls(solver_name)

    @pytest.mark.parametrize("solver_name", ["GradientDescent", "BFGS", "ProximalGradient", "AGradientDescent", 1])
    def test_set_solver_name_allowed(self, solver_name):
        """Test LassoSolver acceptable solvers."""
        acceptable_solvers = [
            "ProximalGradient"
        ]
        solver = self.cls("ProximalGradient")
        raise_exception = solver_name not in acceptable_solvers
        if raise_exception:
            with pytest.raises(ValueError, match=f"Solver `{solver_name}` not allowed for "):
                solver.set_params(solver_name=solver_name)
        else:
            solver.set_params(solver_name=solver_name)

    @pytest.mark.parametrize("solver_kwargs", [{"tol": 10**-10}, {"tols": 10**-10}])
    def test_init_solver_kwargs(self, solver_kwargs):
        """Test LassoSolver acceptable kwargs."""
        raise_exception = "tols" in list(solver_kwargs.keys())
        if raise_exception:
            with pytest.raises(NameError, match="kwargs {'tols'} in solver_kwargs not a kwarg"):
                self.cls("ProximalGradient", solver_kwargs=solver_kwargs)
        else:
            self.cls("ProximalGradient", solver_kwargs=solver_kwargs)

    @pytest.mark.parametrize("loss", [jnp.exp, jax.nn.relu, 1, None, {}])
    def test_loss_callable(self, loss):
        """Test that the loss function is a callable"""
        raise_exception = not callable(loss)
        if raise_exception:
            with pytest.raises(TypeError, match="The loss function must a Callable"):
                self.cls("ProximalGradient").instantiate_solver(loss)
        else:
            self.cls("ProximalGradient").instantiate_solver(loss)

    def test_run_solver(self, poissonGLM_model_instantiation):
        """Test that the solver runs."""

        X, y, model, true_params, firing_rate = poissonGLM_model_instantiation
        runner = self.cls("ProximalGradient").instantiate_solver(model._score)
        runner((true_params[0]*0., true_params[1]), X, y)

    def test_solver_match_statsmodels(self, poissonGLM_model_instantiation):
        """Test that different solvers converge to the same solution."""
        jax.config.update("jax_enable_x64", True)
        X, y, model, true_params, firing_rate = poissonGLM_model_instantiation
        # set precision to float64 for accurate matching of the results
        model.data_type = jnp.float64
        solver = self.cls("ProximalGradient", {"tol": 10**-12})
        runner = solver.instantiate_solver(model._score)
        weights, intercepts = runner((true_params[0] * 0., true_params[1]), X, y)[0]

        # instantiate the glm with statsmodels
        glm_sm = sm.GLM(endog=y[:, 0],
                        exog=sm.add_constant(X[:, 0]),
                        family=sm.families.Poisson())

        # regularize everything except intercept
        alpha_sm = np.ones(X.shape[2] + 1) * solver.regularizer_strength
        alpha_sm[0] = 0

        # pure lasso = elastic net with L1 weight = 1
        res_sm = glm_sm.fit_regularized(method="elastic_net",
                                        alpha=alpha_sm,
                                        L1_wt=1., cnvrg_tol=10**-12)
        # compare params
        sm_params = res_sm.params
        glm_params = jnp.hstack((intercepts, weights.flatten()))
        match_weights = np.allclose(sm_params, glm_params)
        if not match_weights:
            raise ValueError("Lasso GLM solver estimate does not match statsmodels!")


class TestGroupLassoSolver:
    cls = nsl.solver.GroupLassoSolver

    @pytest.mark.parametrize("solver_name", ["GradientDescent", "BFGS", "ProximalGradient", "AGradientDescent", 1])
    def test_init_solver_name(self, solver_name):
        """Test GroupLassoSolver acceptable solvers."""
        acceptable_solvers = [
            "ProximalGradient"
        ]
        raise_exception = solver_name not in acceptable_solvers

        # create a valid mask
        mask = np.zeros((2, 10))
        mask[0, :5] = 1
        mask[1, 5:] = 1
        mask = jnp.asarray(mask)

        if raise_exception:
            with pytest.raises(ValueError, match=f"Solver `{solver_name}` not allowed for "):
                self.cls(solver_name, mask)
        else:
            self.cls(solver_name, mask)

    @pytest.mark.parametrize("solver_name", ["GradientDescent", "BFGS", "ProximalGradient", "AGradientDescent", 1])
    def test_set_solver_name_allowed(self, solver_name):
        """Test GroupLassoSolver acceptable solvers."""
        acceptable_solvers = [
            "ProximalGradient"
        ]
        # create a valid mask
        mask = np.zeros((2, 10))
        mask[0, :5] = 1
        mask[1, 5:] = 1
        mask = jnp.asarray(mask)
        solver = self.cls("ProximalGradient", mask=mask)
        raise_exception = solver_name not in acceptable_solvers
        if raise_exception:
            with pytest.raises(ValueError, match=f"Solver `{solver_name}` not allowed for "):
                solver.set_params(solver_name=solver_name)
        else:
            solver.set_params(solver_name=solver_name)

    @pytest.mark.parametrize("solver_kwargs", [{"tol": 10**-10}, {"tols": 10**-10}])
    def test_init_solver_kwargs(self, solver_kwargs):
        """Test GroupLassoSolver acceptable kwargs."""
        raise_exception = "tols" in list(solver_kwargs.keys())

        # create a valid mask
        mask = np.zeros((2, 10))
        mask[0, :5] = 1
        mask[0, 1:] = 1
        mask = jnp.asarray(mask)

        if raise_exception:
            with pytest.raises(NameError, match="kwargs {'tols'} in solver_kwargs not a kwarg"):
                self.cls("ProximalGradient", mask, solver_kwargs=solver_kwargs)
        else:
            self.cls("ProximalGradient", mask, solver_kwargs=solver_kwargs)

    @pytest.mark.parametrize("loss", [jnp.exp, jax.nn.relu, 1, None, {}])
    def test_loss_callable(self, loss):
        """Test that the loss function is a callable"""
        raise_exception = not callable(loss)

        # create a valid mask
        mask = np.zeros((2, 10))
        mask[0, :5] = 1
        mask[1, 5:] = 1
        mask = jnp.asarray(mask)

        if raise_exception:
            with pytest.raises(TypeError, match="The loss function must a Callable"):
                self.cls("ProximalGradient", mask).instantiate_solver(loss)
        else:
            self.cls("ProximalGradient", mask).instantiate_solver(loss)

    def test_run_solver(self, poissonGLM_model_instantiation):
        """Test that the solver runs."""

        X, y, model, true_params, firing_rate = poissonGLM_model_instantiation

        # create a valid mask
        mask = np.zeros((2, X.shape[2]))
        mask[0, :2] = 1
        mask[1, 2:] = 1
        mask = jnp.asarray(mask)

        runner = self.cls("ProximalGradient", mask).instantiate_solver(model._score)
        runner((true_params[0]*0., true_params[1]), X, y)

    @pytest.mark.parametrize("n_groups_assign", [0, 1, 2])
    def test_mask_validity_groups(self,
                                  n_groups_assign,
                                  group_sparse_poisson_glm_model_instantiation):
        """Test that mask assigns at most 1 group to each weight."""
        raise_exception = n_groups_assign > 1
        X, y, model, true_params, firing_rate, _ = group_sparse_poisson_glm_model_instantiation

        # create a valid mask
        mask = np.zeros((2, X.shape[2]))
        mask[0, :2] = 1
        mask[1, 2:] = 1

        # change assignment
        if n_groups_assign == 0:
            mask[:, 3] = 0
        elif n_groups_assign == 2:
            mask[:, 3] = 1

        mask = jnp.asarray(mask)

        if raise_exception:
            with pytest.raises(ValueError, match="Incorrect group assignment. "
                                                 "Some of the features"):
                self.cls("ProximalGradient", mask).instantiate_solver(model._score)
        else:
            self.cls("ProximalGradient", mask).instantiate_solver(model._score)



    @pytest.mark.parametrize("set_entry", [0, 1, -1, 2, 2.5])
    def test_mask_validity_entries(self, set_entry, poissonGLM_model_instantiation):
        """Test that mask is composed of 0s and 1s."""
        raise_exception = set_entry not in {0, 1}
        X, y, model, true_params, firing_rate = poissonGLM_model_instantiation

        # create a valid mask
        mask = np.zeros((2, X.shape[2]))
        mask[0, :2] = 1
        mask[1, 2:] = 1
        # assign an entry
        mask[1, 2] = set_entry
        mask = jnp.asarray(mask, dtype=jnp.float32)

        if raise_exception:
            with pytest.raises(ValueError, match="Mask elements be 0s and 1s"):
                self.cls("ProximalGradient", mask).instantiate_solver(model._score)
        else:
            self.cls("ProximalGradient", mask).instantiate_solver(model._score)

    @pytest.mark.parametrize("n_dim", [0, 1, 2, 3])
    def test_mask_dimension(self, n_dim, poissonGLM_model_instantiation):
        """Test that mask is composed of 0s and 1s."""

        raise_exception = n_dim != 2
        X, y, model, true_params, firing_rate = poissonGLM_model_instantiation

        # create a valid mask
        if n_dim == 0:
            mask = np.array([])
        elif n_dim == 1:
            mask = np.ones((1,))
        elif n_dim == 2:
            mask = np.zeros((2, X.shape[2]))
            mask[0, :2] = 1
            mask[1, 2:] = 1
        else:
            mask = np.zeros((2, X.shape[2]) + (1, ) * (n_dim-2))
            mask[0, :2] = 1
            mask[1, 2:] = 1

        mask = jnp.asarray(mask, dtype=jnp.float32)

        if raise_exception:
            with pytest.raises(ValueError, match="`mask` must be 2-dimensional"):
                self.cls("ProximalGradient", mask).instantiate_solver(model._score)
        else:
            self.cls("ProximalGradient", mask).instantiate_solver(model._score)

    @pytest.mark.parametrize("n_groups", [0, 1, 2])
    def test_mask_n_groups(self, n_groups, poissonGLM_model_instantiation):
        """Test that mask has at least 1 group."""
        raise_exception = n_groups < 1
        X, y, model, true_params, firing_rate = poissonGLM_model_instantiation

        # create a mask
        mask = np.zeros((n_groups, X.shape[2]))
        if n_groups > 0:
            for i in range(n_groups-1):
                mask[i, i: i+1] = 1
            mask[-1, n_groups-1:] = 1

        mask = jnp.asarray(mask, dtype=jnp.float32)

        if raise_exception:
            with pytest.raises(ValueError, match=r"Empty mask provided! Mask has "):
                self.cls("ProximalGradient", mask).instantiate_solver(model._score)
        else:
            self.cls("ProximalGradient", mask).instantiate_solver(model._score)

    def test_group_sparsity_enforcement(self, group_sparse_poisson_glm_model_instantiation):
        """Test that group lasso works on a simple dataset."""
        X, y, model, true_params, firing_rate, _ = group_sparse_poisson_glm_model_instantiation
        zeros_true = true_params[0].flatten() == 0
        mask = np.zeros((2, X.shape[2]))
        mask[0, zeros_true] = 1
        mask[1, ~zeros_true] = 1
        mask = jnp.asarray(mask, dtype=jnp.float32)

        runner = self.cls("ProximalGradient", mask).instantiate_solver(model._score)
        params, _ = runner((true_params[0]*0., true_params[1]), X, y)

        zeros_est = params[0] == 0
        if not np.all(zeros_est == zeros_true):
            raise ValueError("GroupLasso failed to zero-out the parameter group!")


    ###########
    # Test mask from set_params
    ###########
    @pytest.mark.parametrize("n_groups_assign", [0, 1, 2])
    def test_mask_validity_groups_set_params(self,
                                  n_groups_assign,
                                  group_sparse_poisson_glm_model_instantiation):
        """Test that mask assigns at most 1 group to each weight."""
        raise_exception = n_groups_assign > 1
        X, y, model, true_params, firing_rate, _ = group_sparse_poisson_glm_model_instantiation

        # create a valid mask
        mask = np.zeros((2, X.shape[2]))
        mask[0, :2] = 1
        mask[1, 2:] = 1
        solver = self.cls("ProximalGradient", mask)

        # change assignment
        if n_groups_assign == 0:
            mask[:, 3] = 0
        elif n_groups_assign == 2:
            mask[:, 3] = 1

        mask = jnp.asarray(mask)

        if raise_exception:
            with pytest.raises(ValueError, match="Incorrect group assignment. "
                                                 "Some of the features"):
                solver.set_params(mask=mask)
        else:
            solver.set_params(mask=mask)

    @pytest.mark.parametrize("set_entry", [0, 1, -1, 2, 2.5])
    def test_mask_validity_entries_set_params(self, set_entry, poissonGLM_model_instantiation):
        """Test that mask is composed of 0s and 1s."""
        raise_exception = set_entry not in {0, 1}
        X, y, model, true_params, firing_rate = poissonGLM_model_instantiation

        # create a valid mask
        mask = np.zeros((2, X.shape[2]))
        mask[0, :2] = 1
        mask[1, 2:] = 1
        solver = self.cls("ProximalGradient", mask)

        # assign an entry
        mask[1, 2] = set_entry
        mask = jnp.asarray(mask, dtype=jnp.float32)

        if raise_exception:
            with pytest.raises(ValueError, match="Mask elements be 0s and 1s"):
                solver.set_params(mask=mask)
        else:
            solver.set_params(mask=mask)

    @pytest.mark.parametrize("n_dim", [0, 1, 2, 3])
    def test_mask_dimension(self, n_dim, poissonGLM_model_instantiation):
        """Test that mask is composed of 0s and 1s."""

        raise_exception = n_dim != 2
        X, y, model, true_params, firing_rate = poissonGLM_model_instantiation

        valid_mask = np.zeros((2, X.shape[2]))
        valid_mask[0, :1] = 1
        valid_mask[1, 1:] = 1
        solver = self.cls("ProximalGradient", valid_mask)

        # create a mask
        if n_dim == 0:
            mask = np.array([])
        elif n_dim == 1:
            mask = np.ones((1,))
        elif n_dim == 2:
            mask = np.zeros((2, X.shape[2]))
            mask[0, :2] = 1
            mask[1, 2:] = 1
        else:
            mask = np.zeros((2, X.shape[2]) + (1,) * (n_dim - 2))
            mask[0, :2] = 1
            mask[1, 2:] = 1

        mask = jnp.asarray(mask, dtype=jnp.float32)

        if raise_exception:
            with pytest.raises(ValueError, match="`mask` must be 2-dimensional"):
                solver.set_params(mask=mask)
        else:
            solver.set_params(mask=mask)

    @pytest.mark.parametrize("n_groups", [0, 1, 2])
    def test_mask_n_groups_set_params(self, n_groups, poissonGLM_model_instantiation):
        """Test that mask has at least 1 group."""
        raise_exception = n_groups < 1
        X, y, model, true_params, firing_rate = poissonGLM_model_instantiation
        valid_mask = np.zeros((2, X.shape[2]))
        valid_mask[0, :1] = 1
        valid_mask[1, 1:] = 1
        solver = self.cls("ProximalGradient", valid_mask)

        # create a mask
        mask = np.zeros((n_groups, X.shape[2]))
        if n_groups > 0:
            for i in range(n_groups - 1):
                mask[i, i: i + 1] = 1
            mask[-1, n_groups - 1:] = 1

        mask = jnp.asarray(mask, dtype=jnp.float32)

        if raise_exception:
            with pytest.raises(ValueError, match=r"Empty mask provided! Mask has "):
                solver.set_params(mask=mask)
        else:
            solver.set_params(mask=mask)

