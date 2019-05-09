from typing import Union

import tensorflow as tf

from .dispatch import expectation_dispatch, expectation
from .. import kernels
from .. import mean_functions as mfn
from ..features import InducingFeature, InducingPoints
from ..probability_distributions import (DiagonalGaussian, Gaussian,
                                         MarkovGaussian)
from ..util import NoneType


# ================ exKxz transpose and mean function handling =================

@expectation_dispatch
def _E(p: Union[MarkovGaussian, Gaussian], mean: mfn.Identity, _: NoneType, kernel: kernels.Linear,
       feature: InducingPoints, nghp=None):
    """
    Compute the expectation:
    expectation[n] = <x_n K_{x_n, Z}>_p(x_n)
        - K_{.,} :: Linear kernel
    or the equivalent for MarkovGaussian

    :return: NxDxM
    """
    return tf.linalg.adjoint(expectation(p, (kernel, feature), mean))


@expectation_dispatch
def _E(p: Union[MarkovGaussian, Gaussian], kernel: kernels.Kernel, feature: InducingFeature,
       mean: mfn.MeanFunction, _: NoneType, nghp=None):
    """
    Compute the expectation:
    expectation[n] = <K_{Z, x_n} m(x_n)>_p(x_n)
    or the equivalent for MarkovGaussian

    :return: NxMxQ
    """
    return tf.linalg.adjoint(expectation(p, mean, (kernel, feature), nghp=nghp))


@expectation_dispatch
def _E(p: Gaussian, constant_mean: mfn.Constant, _: NoneType, kernel: kernels.Kernel,
       feature: InducingPoints, nghp=None):
    """
    Compute the expectation:
    expectation[n] = <m(x_n)^T K_{x_n, Z}>_p(x_n)
        - m(x_i) = c :: Constant function
        - K_{.,.}    :: Kernel function

    :return: NxQxM
    """
    c = constant_mean(p.mu)  # NxQ
    eKxz = expectation(p, (kernel, feature), nghp=nghp)  # NxM

    return c[..., None] * eKxz[:, None, :]


@expectation_dispatch
def _E(p: Gaussian, linear_mean: mfn.Linear, _: NoneType, kernel: kernels.Kernel,
       feature: InducingPoints, nghp=None):
    """
    Compute the expectation:
    expectation[n] = <m(x_n)^T K_{x_n, Z}>_p(x_n)
        - m(x_i) = A x_i + b :: Linear mean function
        - K_{.,.}            :: Kernel function

    :return: NxQxM
    """
    N = p.mu.shape[0]
    D = p.mu.shape[1]
    exKxz = expectation(p, mfn.Identity(D), (kernel, feature), nghp=nghp)
    eKxz = expectation(p, (kernel, feature), nghp=nghp)
    eAxKxz = tf.linalg.matmul(tf.tile(linear_mean.A[None, :, :], (N, 1, 1)), exKxz,
                              transpose_a=True)
    ebKxz = linear_mean.b[None, :, None] * eKxz[:, None, :]
    return eAxKxz + ebKxz


@expectation_dispatch
def _E(p: Gaussian, identity_mean: mfn.Identity, _: NoneType, kernel: kernels.Kernel,
       feature: InducingPoints, nghp=None):
    """
    This prevents infinite recursion for kernels that don't have specific
    implementations of _expectation(p, identity_mean, None, kernel, feature).
    Recursion can arise because Identity is a subclass of Linear mean function
    so _expectation(p, linear_mean, none, kernel, feature) would call itself.
    More specific signatures (e.g. (p, identity_mean, None, RBF, feature)) will
    be found and used whenever available
    """
    raise NotImplementedError


# ============== Conversion to Gaussian from Diagonal or Markov ===============
# Catching missing DiagonalGaussian implementations by converting to full Gaussian:


@expectation_dispatch
def _E(p: DiagonalGaussian, obj1: object, feat1: Union[InducingFeature, NoneType],
       obj2: object, feat2: Union[InducingFeature, NoneType], nghp=None):
    gaussian = Gaussian(p.mu, tf.linalg.diag(p.cov))
    return expectation(gaussian, (obj1, feat1), (obj2, feat2), nghp=nghp)


# Catching missing MarkovGaussian implementations by converting to Gaussian (when indifferent):

@expectation_dispatch
def _E(p: MarkovGaussian, obj1: object, feat1: Union[InducingFeature, NoneType],
       obj2: object, feat2: Union[InducingFeature, NoneType], nghp=None):
    """
    Nota Bene: if only one object is passed, obj1 is
    associated with x_n, whereas obj2 with x_{n+1}

    """
    if obj2 is None:
        gaussian = Gaussian(p.mu[:-1], p.cov[0, :-1])
        return expectation(gaussian, (obj1, feat1), nghp=nghp)
    elif obj1 is None:
        gaussian = Gaussian(p.mu[1:], p.cov[0, 1:])
        return expectation(gaussian, (obj2, feat2), nghp=nghp)
    else:
        return expectation(p, (obj1, feat1), (obj2, feat2), nghp=nghp)
