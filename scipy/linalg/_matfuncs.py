#
# Author: Travis Oliphant, March 2002
#
from itertools import product

import numpy as np
from numpy import (dot, diag, prod, logical_not, ravel, transpose,
                   conjugate, absolute, amax, sign, isfinite, triu)
from numpy.lib.scimath import sqrt as csqrt

# Local imports
from scipy.linalg import LinAlgError, bandwidth
from ._misc import norm
from ._basic import solve, inv
from ._decomp_svd import svd
from ._decomp_schur import schur, rsf2csf
from ._expm_frechet import expm_frechet, expm_cond
from ._matfuncs_sqrtm import sqrtm
from ._matfuncs_expm import pick_pade_structure, pade_UV_calc

# deprecated imports to be removed in SciPy 1.13.0
from numpy import single  # noqa

__all__ = ['expm', 'cosm', 'sinm', 'tanm', 'coshm', 'sinhm', 'tanhm', 'logm',
           'funm', 'signm', 'sqrtm', 'fractional_matrix_power', 'expm_frechet',
           'expm_cond', 'khatri_rao']

eps = np.finfo('d').eps
feps = np.finfo('f').eps

_array_precision = {'i': 1, 'l': 1, 'f': 0, 'd': 1, 'F': 0, 'D': 1}


###############################################################################
# Utility functions.


def _asarray_square(A):
    """
    Wraps asarray with the extra requirement that the input be a square matrix.

    The motivation is that the matfuncs module has real functions that have
    been lifted to square matrix functions.

    Parameters
    ----------
    A : array_like
        A square matrix.

    Returns
    -------
    out : ndarray
        An ndarray copy or view or other representation of A.

    """
    A = np.asarray(A)
    if len(A.shape) != 2 or A.shape[0] != A.shape[1]:
        raise ValueError('expected square array_like input')
    return A


def _maybe_real(A, B, tol=None):
    """
    Return either B or the real part of B, depending on properties of A and B.

    The motivation is that B has been computed as a complicated function of A,
    and B may be perturbed by negligible imaginary components.
    If A is real and B is complex with small imaginary components,
    then return a real copy of B.  The assumption in that case would be that
    the imaginary components of B are numerical artifacts.

    Parameters
    ----------
    A : ndarray
        Input array whose type is to be checked as real vs. complex.
    B : ndarray
        Array to be returned, possibly without its imaginary part.
    tol : float
        Absolute tolerance.

    Returns
    -------
    out : real or complex array
        Either the input array B or only the real part of the input array B.

    """
    # Note that booleans and integers compare as real.
    if np.isrealobj(A) and np.iscomplexobj(B):
        if tol is None:
            tol = {0:feps*1e3, 1:eps*1e6}[_array_precision[B.dtype.char]]
        if np.allclose(B.imag, 0.0, atol=tol):
            B = B.real
    return B


###############################################################################
# Matrix functions.


def fractional_matrix_power(A, t):
    """
    Compute the fractional power of a matrix.

    Proceeds according to the discussion in section (6) of [1]_.

    Parameters
    ----------
    A : (N, N) array_like
        Matrix whose fractional power to evaluate.
    t : float
        Fractional power.

    Returns
    -------
    X : (N, N) array_like
        The fractional power of the matrix.

    References
    ----------
    .. [1] Nicholas J. Higham and Lijing lin (2011)
           "A Schur-Pade Algorithm for Fractional Powers of a Matrix."
           SIAM Journal on Matrix Analysis and Applications,
           32 (3). pp. 1056-1078. ISSN 0895-4798

    Examples
    --------
    >>> import numpy as np
    >>> from scipy.linalg import fractional_matrix_power
    >>> a = np.array([[1.0, 3.0], [1.0, 4.0]])
    >>> b = fractional_matrix_power(a, 0.5)
    >>> b
    array([[ 0.75592895,  1.13389342],
           [ 0.37796447,  1.88982237]])
    >>> np.dot(b, b)      # Verify square root
    array([[ 1.,  3.],
           [ 1.,  4.]])

    """
    # This fixes some issue with imports;
    # this function calls onenormest which is in scipy.sparse.
    A = _asarray_square(A)
    import scipy.linalg._matfuncs_inv_ssq
    return scipy.linalg._matfuncs_inv_ssq._fractional_matrix_power(A, t)


def logm(A, disp=True):
    """
    Compute matrix logarithm.

    The matrix logarithm is the inverse of
    expm: expm(logm(`A`)) == `A`

    Parameters
    ----------
    A : (N, N) array_like
        Matrix whose logarithm to evaluate
    disp : bool, optional
        Print warning if error in the result is estimated large
        instead of returning estimated error. (Default: True)

    Returns
    -------
    logm : (N, N) ndarray
        Matrix logarithm of `A`
    errest : float
        (if disp == False)

        1-norm of the estimated error, ||err||_1 / ||A||_1

    References
    ----------
    .. [1] Awad H. Al-Mohy and Nicholas J. Higham (2012)
           "Improved Inverse Scaling and Squaring Algorithms
           for the Matrix Logarithm."
           SIAM Journal on Scientific Computing, 34 (4). C152-C169.
           ISSN 1095-7197

    .. [2] Nicholas J. Higham (2008)
           "Functions of Matrices: Theory and Computation"
           ISBN 978-0-898716-46-7

    .. [3] Nicholas J. Higham and Lijing lin (2011)
           "A Schur-Pade Algorithm for Fractional Powers of a Matrix."
           SIAM Journal on Matrix Analysis and Applications,
           32 (3). pp. 1056-1078. ISSN 0895-4798

    Examples
    --------
    >>> import numpy as np
    >>> from scipy.linalg import logm, expm
    >>> a = np.array([[1.0, 3.0], [1.0, 4.0]])
    >>> b = logm(a)
    >>> b
    array([[-1.02571087,  2.05142174],
           [ 0.68380725,  1.02571087]])
    >>> expm(b)         # Verify expm(logm(a)) returns a
    array([[ 1.,  3.],
           [ 1.,  4.]])

    """
    A = _asarray_square(A)
    # Avoid circular import ... this is OK, right?
    import scipy.linalg._matfuncs_inv_ssq
    F = scipy.linalg._matfuncs_inv_ssq._logm(A)
    F = _maybe_real(A, F)
    errtol = 1000*eps
    #TODO use a better error approximation
    errest = norm(expm(F)-A,1) / norm(A,1)
    if disp:
        if not isfinite(errest) or errest >= errtol:
            print("logm result may be inaccurate, approximate err =", errest)
        return F
    else:
        return F, errest


def expm(A):
    """Compute the matrix exponential of an array.

    Parameters
    ----------
    A : ndarray
        Input with last two dimensions are square ``(..., n, n)``.

    Returns
    -------
    eA : ndarray
        The resulting matrix exponential with the same shape of ``A``

    Notes
    -----
    Implements the algorithm given in [1], which is essentially a Pade
    approximation with a variable order that is decided based on the array
    data.

    For input with size ``n``, the memory usage is in the worst case in the
    order of ``8*(n**2)``. If the input data is not of single and double
    precision of real and complex dtypes, it is copied to a new array.

    For cases ``n >= 400``, the exact 1-norm computation cost, breaks even with
    1-norm estimation and from that point on the estimation scheme given in
    [2] is used to decide on the approximation order.

    References
    ----------
    .. [1] Awad H. Al-Mohy and Nicholas J. Higham, (2009), "A New Scaling
           and Squaring Algorithm for the Matrix Exponential", SIAM J. Matrix
           Anal. Appl. 31(3):970-989, :doi:`10.1137/09074721X`

    .. [2] Nicholas J. Higham and Francoise Tisseur (2000), "A Block Algorithm
           for Matrix 1-Norm Estimation, with an Application to 1-Norm
           Pseudospectra." SIAM J. Matrix Anal. Appl. 21(4):1185-1201,
           :doi:`10.1137/S0895479899356080`

    Examples
    --------
    >>> import numpy as np
    >>> from scipy.linalg import expm, sinm, cosm

    Matrix version of the formula exp(0) = 1:

    >>> expm(np.zeros((3, 2, 2)))
    array([[[1., 0.],
            [0., 1.]],
    <BLANKLINE>
           [[1., 0.],
            [0., 1.]],
    <BLANKLINE>
           [[1., 0.],
            [0., 1.]]])

    Euler's identity (exp(i*theta) = cos(theta) + i*sin(theta))
    applied to a matrix:

    >>> a = np.array([[1.0, 2.0], [-1.0, 3.0]])
    >>> expm(1j*a)
    array([[ 0.42645930+1.89217551j, -2.13721484-0.97811252j],
           [ 1.06860742+0.48905626j, -1.71075555+0.91406299j]])
    >>> cosm(a) + 1j*sinm(a)
    array([[ 0.42645930+1.89217551j, -2.13721484-0.97811252j],
           [ 1.06860742+0.48905626j, -1.71075555+0.91406299j]])

    """
    a = np.asarray(A)
    if a.size == 1 and a.ndim < 2:
        return np.array([[np.exp(a.item())]])

    if a.ndim < 2:
        raise LinAlgError('The input array must be at least two-dimensional')
    if a.shape[-1] != a.shape[-2]:
        raise LinAlgError('Last 2 dimensions of the array must be square')
    n = a.shape[-1]
    # Empty array
    if min(*a.shape) == 0:
        return np.empty_like(a)

    # Scalar case
    if a.shape[-2:] == (1, 1):
        return np.exp(a)

    if not np.issubdtype(a.dtype, np.inexact):
        a = a.astype(float)
    elif a.dtype == np.float16:
        a = a.astype(np.float32)

    # Explicit formula for 2x2 case, formula (2.2) in [1]
    # without Kahan's method numerical instabilities can occur.
    if a.shape[-2:] == (2, 2):
        a1, a2, a3, a4 = (a[..., [0], [0]],
                          a[..., [0], [1]],
                          a[..., [1], [0]],
                          a[..., [1], [1]])
        mu = csqrt((a1-a4)**2 + 4*a2*a3)/2.  # csqrt slow but handles neg.vals

        eApD2 = np.exp((a1+a4)/2.)
        AmD2 = (a1 - a4)/2.
        coshMu = np.cosh(mu)
        sinchMu = np.ones_like(coshMu)
        mask = mu != 0
        sinchMu[mask] = np.sinh(mu[mask]) / mu[mask]
        eA = np.empty((a.shape), dtype=mu.dtype)
        eA[..., [0], [0]] = eApD2 * (coshMu + AmD2*sinchMu)
        eA[..., [0], [1]] = eApD2 * a2 * sinchMu
        eA[..., [1], [0]] = eApD2 * a3 * sinchMu
        eA[..., [1], [1]] = eApD2 * (coshMu - AmD2*sinchMu)
        if np.isrealobj(a):
            return eA.real
        return eA

    # larger problem with unspecified stacked dimensions.
    n = a.shape[-1]
    eA = np.empty(a.shape, dtype=a.dtype)
    # working memory to hold intermediate arrays
    Am = np.empty((5, n, n), dtype=a.dtype)

    # Main loop to go through the slices of an ndarray and passing to expm
    for ind in product(*[range(x) for x in a.shape[:-2]]):
        aw = a[ind]

        lu = bandwidth(aw)
        if not any(lu):  # a is diagonal?
            eA[ind] = np.diag(np.exp(np.diag(aw)))
            continue

        # Generic/triangular case; copy the slice into scratch and send.
        # Am will be mutated by pick_pade_structure
        Am[0, :, :] = aw
        m, s = pick_pade_structure(Am)

        if s != 0:  # scaling needed
            Am[:4] *= [[[2**(-s)]], [[4**(-s)]], [[16**(-s)]], [[64**(-s)]]]

        pade_UV_calc(Am, n, m)
        eAw = Am[0]

        if s != 0:  # squaring needed

            if (lu[1] == 0) or (lu[0] == 0):  # lower/upper triangular
                # This branch implements Code Fragment 2.1 of [1]

                diag_aw = np.diag(aw)
                # einsum returns a writable view
                np.einsum('ii->i', eAw)[:] = np.exp(diag_aw * 2**(-s))
                # super/sub diagonal
                sd = np.diag(aw, k=-1 if lu[1] == 0 else 1)

                for i in range(s-1, -1, -1):
                    eAw = eAw @ eAw

                    # diagonal
                    np.einsum('ii->i', eAw)[:] = np.exp(diag_aw * 2.**(-i))
                    exp_sd = _exp_sinch(diag_aw * (2.**(-i))) * (sd * 2**(-i))
                    if lu[1] == 0:  # lower
                        np.einsum('ii->i', eAw[1:, :-1])[:] = exp_sd
                    else:  # upper
                        np.einsum('ii->i', eAw[:-1, 1:])[:] = exp_sd

            else:  # generic
                for _ in range(s):
                    eAw = eAw @ eAw

        # Zero out the entries from np.empty in case of triangular input
        if (lu[0] == 0) or (lu[1] == 0):
            eA[ind] = np.triu(eAw) if lu[0] == 0 else np.tril(eAw)
        else:
            eA[ind] = eAw

    return eA


def _exp_sinch(x):
    # Higham's formula (10.42), might overflow, see GH-11839
    lexp_diff = np.diff(np.exp(x))
    l_diff = np.diff(x)
    mask_z = l_diff == 0.
    lexp_diff[~mask_z] /= l_diff[~mask_z]
    lexp_diff[mask_z] = np.exp(x[:-1][mask_z])
    return lexp_diff


def cosm(A):
    """
    Compute the matrix cosine.

    This routine uses expm to compute the matrix exponentials.

    Parameters
    ----------
    A : (N, N) array_like
        Input array

    Returns
    -------
    cosm : (N, N) ndarray
        Matrix cosine of A

    Examples
    --------
    >>> import numpy as np
    >>> from scipy.linalg import expm, sinm, cosm

    Euler's identity (exp(i*theta) = cos(theta) + i*sin(theta))
    applied to a matrix:

    >>> a = np.array([[1.0, 2.0], [-1.0, 3.0]])
    >>> expm(1j*a)
    array([[ 0.42645930+1.89217551j, -2.13721484-0.97811252j],
           [ 1.06860742+0.48905626j, -1.71075555+0.91406299j]])
    >>> cosm(a) + 1j*sinm(a)
    array([[ 0.42645930+1.89217551j, -2.13721484-0.97811252j],
           [ 1.06860742+0.48905626j, -1.71075555+0.91406299j]])

    """
    A = _asarray_square(A)
    if np.iscomplexobj(A):
        return 0.5*(expm(1j*A) + expm(-1j*A))
    else:
        return expm(1j*A).real


def sinm(A):
    """
    Compute the matrix sine.

    This routine uses expm to compute the matrix exponentials.

    Parameters
    ----------
    A : (N, N) array_like
        Input array.

    Returns
    -------
    sinm : (N, N) ndarray
        Matrix sine of `A`

    Examples
    --------
    >>> import numpy as np
    >>> from scipy.linalg import expm, sinm, cosm

    Euler's identity (exp(i*theta) = cos(theta) + i*sin(theta))
    applied to a matrix:

    >>> a = np.array([[1.0, 2.0], [-1.0, 3.0]])
    >>> expm(1j*a)
    array([[ 0.42645930+1.89217551j, -2.13721484-0.97811252j],
           [ 1.06860742+0.48905626j, -1.71075555+0.91406299j]])
    >>> cosm(a) + 1j*sinm(a)
    array([[ 0.42645930+1.89217551j, -2.13721484-0.97811252j],
           [ 1.06860742+0.48905626j, -1.71075555+0.91406299j]])

    """
    A = _asarray_square(A)
    if np.iscomplexobj(A):
        return -0.5j*(expm(1j*A) - expm(-1j*A))
    else:
        return expm(1j*A).imag


def tanm(A):
    """
    Compute the matrix tangent.

    This routine uses expm to compute the matrix exponentials.

    Parameters
    ----------
    A : (N, N) array_like
        Input array.

    Returns
    -------
    tanm : (N, N) ndarray
        Matrix tangent of `A`

    Examples
    --------
    >>> import numpy as np
    >>> from scipy.linalg import tanm, sinm, cosm
    >>> a = np.array([[1.0, 3.0], [1.0, 4.0]])
    >>> t = tanm(a)
    >>> t
    array([[ -2.00876993,  -8.41880636],
           [ -2.80626879, -10.42757629]])

    Verify tanm(a) = sinm(a).dot(inv(cosm(a)))

    >>> s = sinm(a)
    >>> c = cosm(a)
    >>> s.dot(np.linalg.inv(c))
    array([[ -2.00876993,  -8.41880636],
           [ -2.80626879, -10.42757629]])

    """
    A = _asarray_square(A)
    return _maybe_real(A, solve(cosm(A), sinm(A)))


def coshm(A):
    """
    Compute the hyperbolic matrix cosine.

    This routine uses expm to compute the matrix exponentials.

    Parameters
    ----------
    A : (N, N) array_like
        Input array.

    Returns
    -------
    coshm : (N, N) ndarray
        Hyperbolic matrix cosine of `A`

    Examples
    --------
    >>> import numpy as np
    >>> from scipy.linalg import tanhm, sinhm, coshm
    >>> a = np.array([[1.0, 3.0], [1.0, 4.0]])
    >>> c = coshm(a)
    >>> c
    array([[ 11.24592233,  38.76236492],
           [ 12.92078831,  50.00828725]])

    Verify tanhm(a) = sinhm(a).dot(inv(coshm(a)))

    >>> t = tanhm(a)
    >>> s = sinhm(a)
    >>> t - s.dot(np.linalg.inv(c))
    array([[  2.72004641e-15,   4.55191440e-15],
           [  0.00000000e+00,  -5.55111512e-16]])

    """
    A = _asarray_square(A)
    return _maybe_real(A, 0.5 * (expm(A) + expm(-A)))


def sinhm(A):
    """
    Compute the hyperbolic matrix sine.

    This routine uses expm to compute the matrix exponentials.

    Parameters
    ----------
    A : (N, N) array_like
        Input array.

    Returns
    -------
    sinhm : (N, N) ndarray
        Hyperbolic matrix sine of `A`

    Examples
    --------
    >>> import numpy as np
    >>> from scipy.linalg import tanhm, sinhm, coshm
    >>> a = np.array([[1.0, 3.0], [1.0, 4.0]])
    >>> s = sinhm(a)
    >>> s
    array([[ 10.57300653,  39.28826594],
           [ 13.09608865,  49.86127247]])

    Verify tanhm(a) = sinhm(a).dot(inv(coshm(a)))

    >>> t = tanhm(a)
    >>> c = coshm(a)
    >>> t - s.dot(np.linalg.inv(c))
    array([[  2.72004641e-15,   4.55191440e-15],
           [  0.00000000e+00,  -5.55111512e-16]])

    """
    A = _asarray_square(A)
    return _maybe_real(A, 0.5 * (expm(A) - expm(-A)))


def tanhm(A):
    """
    Compute the hyperbolic matrix tangent.

    This routine uses expm to compute the matrix exponentials.

    Parameters
    ----------
    A : (N, N) array_like
        Input array

    Returns
    -------
    tanhm : (N, N) ndarray
        Hyperbolic matrix tangent of `A`

    Examples
    --------
    >>> import numpy as np
    >>> from scipy.linalg import tanhm, sinhm, coshm
    >>> a = np.array([[1.0, 3.0], [1.0, 4.0]])
    >>> t = tanhm(a)
    >>> t
    array([[ 0.3428582 ,  0.51987926],
           [ 0.17329309,  0.86273746]])

    Verify tanhm(a) = sinhm(a).dot(inv(coshm(a)))

    >>> s = sinhm(a)
    >>> c = coshm(a)
    >>> t - s.dot(np.linalg.inv(c))
    array([[  2.72004641e-15,   4.55191440e-15],
           [  0.00000000e+00,  -5.55111512e-16]])

    """
    A = _asarray_square(A)
    return _maybe_real(A, solve(coshm(A), sinhm(A)))


def funm(A, func, disp=True):
    """
    Evaluate a matrix function specified by a callable.

    Returns the value of matrix-valued function ``f`` at `A`. The
    function ``f`` is an extension of the scalar-valued function `func`
    to matrices.

    Parameters
    ----------
    A : (N, N) array_like
        Matrix at which to evaluate the function
    func : callable
        Callable object that evaluates a scalar function f.
        Must be vectorized (eg. using vectorize).
    disp : bool, optional
        Print warning if error in the result is estimated large
        instead of returning estimated error. (Default: True)

    Returns
    -------
    funm : (N, N) ndarray
        Value of the matrix function specified by func evaluated at `A`
    errest : float
        (if disp == False)

        1-norm of the estimated error, ||err||_1 / ||A||_1

    Notes
    -----
    This function implements the general algorithm based on Schur decomposition
    (Algorithm 9.1.1. in [1]_).

    If the input matrix is known to be diagonalizable, then relying on the
    eigendecomposition is likely to be faster. For example, if your matrix is
    Hermitian, you can do

    >>> from scipy.linalg import eigh
    >>> def funm_herm(a, func, check_finite=False):
    ...     w, v = eigh(a, check_finite=check_finite)
    ...     ## if you further know that your matrix is positive semidefinite,
    ...     ## you can optionally guard against precision errors by doing
    ...     # w = np.maximum(w, 0)
    ...     w = func(w)
    ...     return (v * w).dot(v.conj().T)

    References
    ----------
    .. [1] Gene H. Golub, Charles F. van Loan, Matrix Computations 4th ed.

    Examples
    --------
    >>> import numpy as np
    >>> from scipy.linalg import funm
    >>> a = np.array([[1.0, 3.0], [1.0, 4.0]])
    >>> funm(a, lambda x: x*x)
    array([[  4.,  15.],
           [  5.,  19.]])
    >>> a.dot(a)
    array([[  4.,  15.],
           [  5.,  19.]])

    """
    A = _asarray_square(A)
    # Perform Shur decomposition (lapack ?gees)
    T, Z = schur(A)
    T, Z = rsf2csf(T,Z)
    n,n = T.shape
    F = diag(func(diag(T)))  # apply function to diagonal elements
    F = F.astype(T.dtype.char)  # e.g., when F is real but T is complex

    minden = abs(T[0,0])

    # implement Algorithm 11.1.1 from Golub and Van Loan
    #                 "matrix Computations."
    for p in range(1,n):
        for i in range(1,n-p+1):
            j = i + p
            s = T[i-1,j-1] * (F[j-1,j-1] - F[i-1,i-1])
            ksl = slice(i,j-1)
            val = dot(T[i-1,ksl],F[ksl,j-1]) - dot(F[i-1,ksl],T[ksl,j-1])
            s = s + val
            den = T[j-1,j-1] - T[i-1,i-1]
            if den != 0.0:
                s = s / den
            F[i-1,j-1] = s
            minden = min(minden,abs(den))

    F = dot(dot(Z, F), transpose(conjugate(Z)))
    F = _maybe_real(A, F)

    tol = {0:feps, 1:eps}[_array_precision[F.dtype.char]]
    if minden == 0.0:
        minden = tol
    err = min(1, max(tol,(tol/minden)*norm(triu(T,1),1)))
    if prod(ravel(logical_not(isfinite(F))),axis=0):
        err = np.inf
    if disp:
        if err > 1000*tol:
            print("funm result may be inaccurate, approximate err =", err)
        return F
    else:
        return F, err


def signm(A, disp=True):
    """
    Matrix sign function.

    Extension of the scalar sign(x) to matrices.

    Parameters
    ----------
    A : (N, N) array_like
        Matrix at which to evaluate the sign function
    disp : bool, optional
        Print warning if error in the result is estimated large
        instead of returning estimated error. (Default: True)

    Returns
    -------
    signm : (N, N) ndarray
        Value of the sign function at `A`
    errest : float
        (if disp == False)

        1-norm of the estimated error, ||err||_1 / ||A||_1

    Examples
    --------
    >>> from scipy.linalg import signm, eigvals
    >>> a = [[1,2,3], [1,2,1], [1,1,1]]
    >>> eigvals(a)
    array([ 4.12488542+0.j, -0.76155718+0.j,  0.63667176+0.j])
    >>> eigvals(signm(a))
    array([-1.+0.j,  1.+0.j,  1.+0.j])

    """
    A = _asarray_square(A)

    def rounded_sign(x):
        rx = np.real(x)
        if rx.dtype.char == 'f':
            c = 1e3*feps*amax(x)
        else:
            c = 1e3*eps*amax(x)
        return sign((absolute(rx) > c) * rx)
    result, errest = funm(A, rounded_sign, disp=0)
    errtol = {0:1e3*feps, 1:1e3*eps}[_array_precision[result.dtype.char]]
    if errest < errtol:
        return result

    # Handle signm of defective matrices:

    # See "E.D.Denman and J.Leyva-Ramos, Appl.Math.Comp.,
    # 8:237-250,1981" for how to improve the following (currently a
    # rather naive) iteration process:

    # a = result # sometimes iteration converges faster but where??

    # Shifting to avoid zero eigenvalues. How to ensure that shifting does
    # not change the spectrum too much?
    vals = svd(A, compute_uv=False)
    max_sv = np.amax(vals)
    # min_nonzero_sv = vals[(vals>max_sv*errtol).tolist().count(1)-1]
    # c = 0.5/min_nonzero_sv
    c = 0.5/max_sv
    S0 = A + c*np.identity(A.shape[0])
    prev_errest = errest
    for i in range(100):
        iS0 = inv(S0)
        S0 = 0.5*(S0 + iS0)
        Pp = 0.5*(dot(S0,S0)+S0)
        errest = norm(dot(Pp,Pp)-Pp,1)
        if errest < errtol or prev_errest == errest:
            break
        prev_errest = errest
    if disp:
        if not isfinite(errest) or errest >= errtol:
            print("signm result may be inaccurate, approximate err =", errest)
        return S0
    else:
        return S0, errest


def khatri_rao(a, b):
    r"""
    Khatri-rao product

    A column-wise Kronecker product of two matrices

    Parameters
    ----------
    a : (n, k) array_like
        Input array
    b : (m, k) array_like
        Input array

    Returns
    -------
    c:  (n*m, k) ndarray
        Khatri-rao product of `a` and `b`.

    See Also
    --------
    kron : Kronecker product

    Notes
    -----
    The mathematical definition of the Khatri-Rao product is:

    .. math::

        (A_{ij}  \bigotimes B_{ij})_{ij}

    which is the Kronecker product of every column of A and B, e.g.::

        c = np.vstack([np.kron(a[:, k], b[:, k]) for k in range(b.shape[1])]).T

    Examples
    --------
    >>> import numpy as np
    >>> from scipy import linalg
    >>> a = np.array([[1, 2, 3], [4, 5, 6]])
    >>> b = np.array([[3, 4, 5], [6, 7, 8], [2, 3, 9]])
    >>> linalg.khatri_rao(a, b)
    array([[ 3,  8, 15],
           [ 6, 14, 24],
           [ 2,  6, 27],
           [12, 20, 30],
           [24, 35, 48],
           [ 8, 15, 54]])

    """
    a = np.asarray(a)
    b = np.asarray(b)

    if not (a.ndim == 2 and b.ndim == 2):
        raise ValueError("The both arrays should be 2-dimensional.")

    if not a.shape[1] == b.shape[1]:
        raise ValueError("The number of columns for both arrays "
                         "should be equal.")

    # c = np.vstack([np.kron(a[:, k], b[:, k]) for k in range(b.shape[1])]).T
    c = a[..., :, np.newaxis, :] * b[..., np.newaxis, :, :]
    return c.reshape((-1,) + c.shape[2:])


def matrix_similarity_transform(A, P):
    """
    Perform a matrix similarity transformation on matrix A using matrix P.

    Parameters
    ----------
    A : array_like
        The input matrix to be transformed.
    P : array_like
        The transformation matrix.

    Returns
    -------
    B : ndarray
        The transformed matrix.

    Raises
    ------
    ValueError
        If the dimensions of A and P are not compatible for the transformation.

    """
    A = np.asarray(A)
    P = np.asarray(P)

    if A.shape[0] != A.shape[1] or P.shape[0] != P.shape[1]:
        raise ValueError('Both matrices must be square.')

    if A.shape != P.shape:
        raise ValueError('The dimensions of A and P must be the same.')

    P_inv = np.linalg.inv(P)
    B = P_inv.dot(A).dot(P)

    return B


def rotate_matrix(matrix, angle_degrees):
    """
    Rotate a 2D matrix by a specified angle in degrees.

    Parameters
    ----------
    matrix : array_like
        The input 2D matrix to be rotated.
    angle_degrees : float
        The rotation angle in degrees.

    Returns
    -------
    rotated_matrix : ndarray
        The rotated matrix.

    """
    # Convert angle from degrees to radians
    angle_radians = np.radians(angle_degrees)
    
    # Create a 2x2 rotation matrix
    rotation_matrix = np.array([[np.cos(angle_radians), -np.sin(angle_radians)],
                                 [np.sin(angle_radians), np.cos(angle_radians)]])
    
    # Perform the matrix multiplication to rotate the input matrix
    rotated_matrix = np.dot(rotation_matrix, matrix)
    
    return rotated_matrix


def scale_matrix(matrix, scaling_factor):
    """
    Scale a matrix by a specified scaling factor.

    Parameters
    ----------
    matrix : array_like
        The input matrix to be scaled.
    scaling_factor : float
        The scaling factor by which to multiply the matrix.

    Returns
    -------
    scaled_matrix : ndarray
        The scaled matrix.

    """
    # Convert the input matrix to a NumPy array
    matrix = np.asarray(matrix)
    
    # Perform the matrix scaling
    scaled_matrix = matrix * scaling_factor
    
    return scaled_matrix


def matdiff_matrix(matrix, scalar_var, epsilon=1e-6):
    """
    Approximate the derivative of a matrix with respect to a scalar variable using finite differences.

    Parameters
    ----------
    matrix : array_like
        The input matrix to be differentiated.
    scalar_var : float
        The scalar variable with respect to which differentiation is performed.
    epsilon : float, optional
        A small value to use for finite differences (default is 1e-6).

    Returns
    -------
    derivative_matrix : ndarray
        The approximate derivative matrix.

    """
    matrix = np.asarray(matrix, dtype=float)
    original_matrix = matrix.copy()
    
    # Create a function that calculates the matrix value given a scalar value
    def matrix_function(scalar):
        matrix[:] = original_matrix  # Reset the matrix to the original value
        matrix *= scalar  # Scale the matrix by the scalar
        return matrix.copy()  # Return a copy to avoid modifying the original
    
    # Calculate the finite difference approximation of the derivative
    derivative_matrix = (matrix_function(scalar_var + epsilon) - matrix_function(scalar_var - epsilon)) / (2 * epsilon)
    
    return derivative_matrix


def proj_matrix(matrix_to_project, target_matrix):
    """
    Project a matrix onto another matrix or subspace.

    Parameters
    ----------
    matrix_to_project : array_like
        The matrix to be projected.
    target_matrix : array_like
        The target matrix onto which the projection is performed.

    Returns
    -------
    projected_matrix : ndarray
        The projected matrix onto the target matrix or subspace.

    """
    # Ensure the input matrices are NumPy arrays
    matrix_to_project = np.asarray(matrix_to_project, dtype=float)
    target_matrix = np.asarray(target_matrix, dtype=float)
    
    # Calculate the projection matrix
    projection_matrix = np.dot(target_matrix, np.linalg.lstsq(target_matrix, matrix_to_project, rcond=None)[0])
    
    return projection_matrix


def concatenate_matrices(matrices, axis=0):
    """
    Concatenate a list of matrices along the specified axis.

    Parameters
    ----------
    matrices : list of array_like
        A list of matrices to be concatenated.
    axis : int, optional
        The axis along which concatenation is performed (default is 0).

    Returns
    -------
    concatenated_matrix : ndarray
        The concatenated matrix.

    """
    # Ensure the input matrices are NumPy arrays
    matrices = [np.asarray(matrix) for matrix in matrices]
    
    # Perform matrix concatenation along the specified axis
    concatenated_matrix = np.concatenate(matrices, axis=axis)
    
    return concatenated_matrix


def kron_matrix(matrix1, matrix2):
    """
    Compute the Kronecker product of two matrices.

    Parameters
    ----------
    matrix1 : array_like
        The first input matrix.
    matrix2 : array_like
        The second input matrix.

    Returns
    -------
    kronecker_product : ndarray
        The Kronecker product of the two matrices.

    """
    # Ensure the input matrices are NumPy arrays
    matrix1 = np.asarray(matrix1)
    matrix2 = np.asarray(matrix2)
    
    # Compute the Kronecker product
    kronecker_product = np.kron(matrix1, matrix2)
    
    return kronecker_product

def matrix_rank(matrix):
    """
    Compute the rank of a matrix.

    Parameters
    ----------
    matrix : array_like
        The input matrix.

    Returns
    -------
    rank : int
        The rank of the matrix.

    """
    # Ensure the input matrix is a NumPy array
    matrix = np.asarray(matrix, dtype=float)
    
    # Compute the rank using NumPy's linalg.matrix_rank function
    rank = np.linalg.matrix_rank(matrix)
    
    return rank


def solve_matrix_equation(matrix_a, matrix_b):
    """
    Solve a system of linear equations represented as matrices (Ax = B).

    Parameters
    ----------
    matrix_a : array_like
        Coefficient matrix (A) of the linear equations.
    matrix_b : array_like
        Right-hand side matrix (B) of the linear equations.

    Returns
    -------
    solution_matrix : ndarray
        The solution matrix (x) of the linear equations.

    """
    # Ensure the input matrices are NumPy arrays
    matrix_a = np.asarray(matrix_a, dtype=float)
    matrix_b = np.asarray(matrix_b, dtype=float)
    
    # Solve the linear equations using NumPy's linalg.solve function
    solution_matrix = np.linalg.solve(matrix_a, matrix_b)
    
    return solution_matrix


def matrix_norm(matrix, norm_type='fro'):
    """
    Compute the specified matrix norm.

    Parameters
    ----------
    matrix : array_like
        The input matrix for which you want to compute the norm.
    norm_type : str, optional
        The type of matrix norm to compute (default is 'fro' for Frobenius norm).
        Supported norm types: 'fro' (Frobenius norm), '1' (1-norm), '2' (2-norm), 'inf' (infinity norm).

    Returns
    -------
    norm_value : float
        The computed matrix norm.

    """
    # Ensure the input matrix is a NumPy array
    matrix = np.asarray(matrix, dtype=float)
    
    # Compute the specified matrix norm
    if norm_type == 'fro':
        norm_value = np.linalg.norm(matrix, ord='fro')
    elif norm_type == '1':
        norm_value = np.linalg.norm(matrix, ord=1)
    elif norm_type == '2':
        norm_value = np.linalg.norm(matrix, ord=2)
    elif norm_type == 'inf':
        norm_value = np.linalg.norm(matrix, ord=np.inf)
    else:
        raise ValueError("Unsupported norm type. Choose from 'fro', '1', '2', or 'inf'.")
    
    return norm_value



def transpose_matrix(matrix):
    """
    Transpose a matrix.

    Parameters
    ----------
    matrix : array_like
        The input matrix to be transposed.

    Returns
    -------
    transposed_matrix : ndarray
        The transposed matrix.

    """
    # Ensure the input matrix is a NumPy array
    matrix = np.asarray(matrix, dtype=float)
    
    # Transpose the matrix using NumPy's transpose or T attribute
    transposed_matrix = np.transpose(matrix)
    # Alternatively, you can use: transposed_matrix = matrix.T
    
    return transposed_matrix


def svd_matrix(matrix):
    """
    Perform Singular Value Decomposition (SVD) of a matrix.

    Parameters
    ----------
    matrix : array_like
        The input matrix for which you want to compute the SVD.

    Returns
    -------
    U : ndarray
        The left singular vectors.
    S : ndarray
        The singular values.
    Vt : ndarray
        The right singular vectors (transposed).

    """
    # Ensure the input matrix is a NumPy array
    matrix = np.asarray(matrix, dtype=float)
    
    # Perform SVD using NumPy's svd function
    U, S, Vt = np.linalg.svd(matrix, full_matrices=True)
    
    return U, S, Vt


def eig_matrix(matrix):
    """
    Compute the eigenvalues and eigenvectors of a matrix.

    Parameters
    ----------
    matrix : array_like
        The input matrix for which you want to compute eigenvalues and eigenvectors.

    Returns
    -------
    eigenvalues : ndarray
        The eigenvalues of the matrix.
    eigenvectors : ndarray
        The corresponding eigenvectors of the matrix.

    """
    # Ensure the input matrix is a NumPy array
    matrix = np.asarray(matrix, dtype=float)
    
    # Compute eigenvalues and eigenvectors using NumPy's eig function
    eigenvalues, eigenvectors = np.linalg.eig(matrix)
    
    return eigenvalues, eigenvectors
  
