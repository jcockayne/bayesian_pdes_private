import numpy as np
import pairwise
from sympy_helpers import sympy_function, n_arg_applier


def generate_op_cache(operators, operators_bar, k, symbols, mode=None, sympy_function_kwargs=None, debug=False):
    ret = {
        tuple(): functionize(k, symbols, mode=mode, sympy_function_kwargs=sympy_function_kwargs)
    }
    for op in operators:
        if op not in ret:
            ret[(op,)] = functionize(op(k), symbols, mode=mode, sympy_function_kwargs=sympy_function_kwargs)
    for op in operators_bar:
        if op not in ret:
            ret[(op,)] = functionize(op(k), symbols, mode=mode, sympy_function_kwargs=sympy_function_kwargs)
    # combinations
    for op in operators:
        for op_bar in operators_bar:
            # don't do anything if already there
            if (op, op_bar) in ret:
                pass
            # exploit symmetry
            elif (op_bar, op) in ret:
                ret[(op, op_bar)] = ret[(op_bar, op)]
            # no choice!!
            else:
                ret[(op, op_bar)] = functionize(op(op_bar(k)), symbols, mode=mode, sympy_function_kwargs=sympy_function_kwargs)
    return ret


def collocate(operators, operators_bar, k, symbols, observations, op_cache=None, fun_args=None):
    """
    Construct a collocation approximation to the system of operators supplied.
    :param operators: List of operators operators (as functions which operate on sympy expressions)
    :param operators_bar: List of operators working on the second argument of the kernel.
    :param k: The kernel itself, as a sympy expression
    :param symbols: Sympy symbols for the kernel. Note that thanks to sympy being a bit peculiar we can't easily use
    vector operations here - instead each component must be supplied separately if we are working in a higher-dimensional
    space.
    In this event, the sympy symbols should be grouped into sub-lists according to which vector they belong to,
    eg. [[x_1, x_2], [y_1, y_2]]
    :param observations: List of observations. Size should match the size of the list of operators.
    It should be a list of tuples, [(obs locations, obs values)], where obs locations has m rows and d columns and
    values has m rows and 1 column. Here m is the number of points observed and d is the dimension of each point.
    :return: A function which, when given a set of test points, returns the posterior mean and covariance at those
    points.
    """
    for locs, vals in observations:
        if vals is None: continue
        err = " (Loc has shape {}, vals have shape {})".format(locs.shape, vals.shape)
        if locs.shape[0] != vals.shape[0]:
            raise Exception("Number of obs not consistent with location of obs " + err)
        if len(locs.shape) != 2:
            raise Exception("Obs locations must be two-dimensional " + err)

    if op_cache is None:
        op_cache = generate_op_cache(operators, operators_bar, k, symbols)

    LLbar = calc_LLbar(operators, operators_bar, observations, op_cache, fun_args)
    # optimization - if the returned object has an inv() method then use that
    # this is to make use of things like the kronecker inverse formula
    if hasattr(LLbar, 'inv'):
        # asarray this so that we aren't doing anything funky every time we .dot
        LLbar_inv = np.asarray(LLbar.inv())
    else:
        LLbar_inv = np.linalg.inv(LLbar)

    # and the observation vector...

    # finally return the posterior
    return CollocationPosterior(operators, operators_bar, op_cache, observations, LLbar_inv, fun_args)


# for now we only support sympy, maybe later support Theano?
# nest inside a function which will apply the result pairwise
def functionize(fun, symbols, mode=None, apply_factory=n_arg_applier, sympy_function_kwargs=None):
    if sympy_function_kwargs is None:
        sympy_function_kwargs = {}
    sympy_fun = sympy_function(fun, symbols, mode=mode, apply_factory=apply_factory, **sympy_function_kwargs)

    def __ret_function(a, b, extra=None):
        return pairwise.apply(sympy_fun, a, b, extra)

    return __ret_function


def calc_LLbar(operators, operators_bar, observations, op_cache, fun_args=None):
    # and build the 2D matrix
    if fun_args is None:
        fun_args = []
    LLbar = []

    for op, obs_1 in zip(operators, observations):
        tmp = []
        for op_bar, obs_2 in zip(operators_bar, observations):
            points_1, _ = obs_1
            points_2, _ = obs_2

            fun_op = op_cache[(op, op_bar)]

            applied = fun_op(points_1, points_2, *fun_args)
            tmp.append(applied)
        LLbar.append(np.hstack(tmp))

    return np.vstack(LLbar)


def calc_side_matrices(operators, operators_bar, obs, test_points, op_cache, fun_args=None):
    if fun_args is None:
        fun_args = []
    obs_points = np.r_[[p for p, _ in obs]]
    L = []
    Lbar = []
    for op, op_bar, point in zip(operators, operators_bar, obs_points):
        f = op_cache[(op,)]
        fbar = op_cache[(op_bar,)]
        L.append(f(point, test_points, *fun_args))
        Lbar.append(fbar(test_points, point, *fun_args))
    L = np.vstack(L)
    Lbar = np.hstack(Lbar)
    return L, Lbar


class CollocationPosterior(object):
    def __init__(self, operators, operators_bar, op_cache, obs, LLbar_inv, fun_args=None):
        self.__operators = operators
        self.__operators_bar = operators_bar
        self.__op_cache = op_cache
        self.__obs = obs
        self.__LLbar_inv = LLbar_inv
        self.__fun_args = [] if fun_args is None else fun_args

    def __call__(self, test_points):
        return self.posterior(test_points)

    def posterior(self, test_points):
        g = np.concatenate([val for _, val in self.__obs])
        mu_multiplier, Sigma = self.no_obs_posterior(test_points)
        return mu_multiplier.dot(g), Sigma

    def no_obs_posterior(self, test_points):
        L, Lbar = calc_side_matrices(self.__operators, self.__operators_bar, self.__obs, test_points, self.__op_cache, self.__fun_args)

        k_eval = self.__op_cache[()]
        mu_multiplier = Lbar.dot(self.__LLbar_inv)
        k_mat = k_eval(test_points, test_points, *self.__fun_args)
        Sigma = k_mat - Lbar.dot(self.__LLbar_inv).dot(L)

        return mu_multiplier, Sigma