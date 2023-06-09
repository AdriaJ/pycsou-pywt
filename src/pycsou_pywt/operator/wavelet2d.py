import warnings

import numpy as np
import pycsou.abc.operator as pyco
import pycsou.runtime as pycrt
import pycsou.util.deps as pycd
import pycsou.util.ptype as pyct
import pycsou.util.warning as pycuw
import pywt

__all__ = [
    "WaveletDec2",
]


class WaveletDec2(pyco.LinOp):
    """
    Linear operator for wavelet coefficients decomposition.
    """

    def __init__(self, input_shape: pyct.NDArrayShape, wavelet_name: str, level: int = None, mode: str = "zero"):
        r"""
        2D Wavelet decomposition operator.

        Returns the 2-dimensional wavelet decomposition coefficients, according to the selected wavelet basis and up to
        the chosen level of details.

        The computations are performed thanks to the Python package `PyWavelets <https://pywavelets.readthedocs.io/en/latest/index.html>`_.
        With a correct set of parameters, the wavelet transform is unitary so that the adjoint can be efficiently
        computed as the inverse transform (also provided by PyWavelets).

        Parameters
        ----------
        input_shape: pyct.NDArrayShape
            (..., m, n) Shape of the images to apply the decomposition of, must be a 2-dimensional tuple.
        wavelet_name: str
            Name of the wavelet basis to use, must be one of the discrete
        level: int
            Decomposition level, must be non-negative. Default is ``None``, the level is set to the maximum level
             possible, computed with `pywt.dwtn_max_level() <https://pywavelets.readthedocs.io/en/latest/ref/dwt-discrete-wavelet-transform.html#pywt.dwtn_max_level>`_.
        mode: str
            Signal extension mode, see `Modes <https://pywavelets.readthedocs.io/en/latest/ref/signal-extension-modes.html#ref-modes>`_
            for the list of available modes. Note that only the mode ``'zero'`` ensures the correct definition of the
            adjoint operator.

        Notes
        -----

        * As per Pycsou guidelines, the operator accepts input with more than two dimensions. The wavelet
          transform is applied to the last two dimensions of the input array (as long as the shape is consistent with
          ``input_shape``).

        * Only the value ``mode='zero'`` ensures that the wavelet decomposition operation is unitary, such that its
          adjoint operator is given by the inverse operator. When used with other values of ``mode``, the adjoint
          operation is no longer valid.

        * The list of discrete wavelets accessible is accessible with
          `pywt.wavelist(kind='discrete') <https://pywavelets.readthedocs.io/en/latest/ref/wavelets.html#built-in-wavelets-wavelist>`_.
          The "Biorthogonal" (``'bior'``) and "Reverse Biorthogonal" (``'rbio'``) wavelet families are not unitary when
          computed with mode ``'zero'``, so the adjoint is no longer correct for these wavelets.

        * The operator only supports Numpy backend so far (needs to be tested for Dask backend, not available for CuPy).

        Example
        -------

        .. code-block:: python3

            import numpy as np
            import pycsou_pywt as pycwt

            image_shape = (45, 60)
            test_image = np.zeros(image_shape)
            test_image[5:15, 10:50] = test_image[30:40, 10:50] = 255
            test_image[20:25, 20:40] = 127

            wl = 'db2'
            level = 2

            op = pycwt.WaveletDec2(image_shape, wl, level=level)

            coeffs = op(test_image)
            proj_image = op.adjoint(coeffs)

            print(proj_image.shape == test_image.shape)

        """
        assert len(input_shape) == 2, f"The input shape must be a size 2 tuple, given has length {len(input_shape)}."
        self.input_shape = input_shape
        if wavelet_name in pywt.wavelist(family="bior") or wavelet_name in pywt.wavelist(family="rbio"):
            raise Warning(
                "Wavelets of the family 'bior' and 'rbio' are not unitary in mode 'zero', the adjoint is not "
                "the inverse transform."
            )
        elif wavelet_name in pywt.wavelist(kind="discrete"):
            self._wavelet = wavelet_name
        elif wavelet_name in pywt.wavelist(kind="continuous"):
            raise ValueError("Must use a discrete wavelet basis. See documentation for the list of available names.")
        else:
            raise ValueError(
                f"'{wavelet_name}' is not a valid name." f"See documentation for the list of available names."
            )
        max_level = pywt.dwtn_max_level(input_shape, wavelet_name)
        if level is None:
            level = max_level
        elif level > max_level:
            level = max_level
            msg = f"Requested level of decomposition too high, auto-corrected to {level}"
            warnings.warn(msg, pycuw.AutoInferenceWarning)
        assert level >= 0, "Decomposition level should non-negative or None."
        self._level = level
        self._mode = mode
        init_coeffs = pywt.wavedec2(np.zeros(self.input_shape), self._wavelet, mode=self._mode, level=self._level)
        arr, slices = pywt.coeffs_to_array(init_coeffs, axes=(-2, -1))
        self.coeff_slices = slices
        self.coeff_shape = arr.shape
        super().__init__(shape=(arr.shape[0] * arr.shape[1], input_shape[0] * input_shape[1]))

        if self._mode == "zero":
            self._lipschitz = 1.0

    @pycrt.enforce_precision(i="arr")
    def apply(self, arr: pyct.NDArray) -> pyct.NDArray:
        raster_image = arr.reshape(*arr.shape[:-1], *self.input_shape)
        coeffs = pywt.wavedec2(
            raster_image,
            self._wavelet,
            mode=self._mode,
            level=self._level,
        )
        return pywt.coeffs_to_array(coeffs, axes=(-2, -1))[0].reshape(*arr.shape[:-1], -1)

    @pycrt.enforce_precision(i="arr")
    def adjoint(self, arr: pyct.NDArray) -> pyct.NDArray:
        raster_arr = arr.reshape(*arr.shape[:-1], *self.coeff_shape)
        if arr.ndim == 1:
            slices = self.coeff_slices
        else:
            _, slices = pywt.coeffs_to_array(
                pywt.wavedec2(np.zeros((*arr.shape[:-1], *self.input_shape)), self._wavelet, level=self._level),
                axes=(-2, -1),
            )
        coeffs = pywt.array_to_coeffs(raster_arr, slices, output_format="wavedec2")
        res = pywt.waverec2(
            coeffs,
            self._wavelet,
            mode=self._mode,
        )
        return self._odd_cropping(res).reshape(*arr.shape[:-1], -1)

    @pycrt.enforce_precision()
    def svdvals(self, **kwargs) -> pyct.NDArray:
        return pyco.UnitOp.svdvals(self, **kwargs)

    @property
    def level(self):
        r"""
        Getter for the attribute ``level``, useful when the value has been auto-set (``None`` input or level too high).
        """
        return self._level

    def _odd_cropping(self, arr: np.ndarray) -> np.ndarray:
        r"""
        If the input image of `pywt.wavedec2() <https://pywavelets.readthedocs.io/en/latest/ref/2d-dwt-and-idwt.html#d-multilevel-decomposition-using-wavedec2>`_
        has an odd size on a given dimension, the reconstructed image by `pywt.waverec2() <hhttps://pywavelets.readthedocs.io/en/latest/ref/2d-dwt-and-idwt.html#d-multilevel-reconstruction-using-waverec2>`_
        will have an extra length on that dimension.
        This function crops the additional pixel so that the output image has the same shape as the input one.

        Parameters
        ----------
        arr: np.ndarray
            (..., n, m) 2D image (or stack of 2D images) returned by :python:`pywt.waverec2()`.

        Returns
        -------
        out: np.ndarray
            (..., *self.image_shape) 2D image with correct size.

        """
        odd_test = [dim % 2 == 1 for dim in self.input_shape]
        if np.any(odd_test):
            s = (slice(None, None, None),) * (np.ndim(arr) - 2) + tuple(
                slice(None, -1 if elem else None, None) for elem in odd_test
            )
            return arr[s]
        else:
            return arr

    def asarray(self, **kwargs) -> pyct.NDArray:
        dtype = kwargs.get("dtype", pycrt.getPrecision().value)
        xp = kwargs.get("xp", pycd.NDArrayInfo.NUMPY.module())

        A = super().asarray(dtype=dtype, xp=np)
        return xp.asarray(A)


# TODO test wavelet 2d and potentially extend to more dimensions
# TODO test dask
