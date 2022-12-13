"""
Minhash encoding of string arrays.
The principle is as follows:
  1. A string is viewed as a succession of numbers (the ASCII or UTF8
     representation of its elements).
  2. The string is then decomposed into a set of n-grams, i.e.
     n-dimensional vectors of integers.
  3. A hashing function is used to assign an integer to each n-gram.
     The minimum of the hashes over all n-grams is used in the encoding.
  4. This process is repeated with N hashing functions are used to
     form N-dimensional encodings.
Maxhash encodings can be computed similarly by taking the hashes maximum
instead.
With this procedure, strings that share many n-grams have greater
probability of having same encoding values. These encodings thus capture
morphological similarities between strings.
"""

from typing import Dict, List, Literal, Tuple

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.utils import murmurhash3_32

from ._fast_hash import ngram_min_hash
from ._string_distances import get_unique_ngrams
from ._utils import LRUDict, check_input

NoneType = type(None)


class MinHashEncoder(BaseEstimator, TransformerMixin):
    """
    Encode string categorical features as a numeric array, minhash method
    applied to ngram decomposition of strings based on ngram decomposition
    of the string.

    Parameters
    ----------
    n_components : int, default=30
        The number of dimension of encoded strings. Numbers around 300 tend to
        lead to good prediction performance, but with more computational cost.
    ngram_range : typing.Tuple[int, int], default=(2, 4)
        The lower and upper boundary of the range of n-values for different
        n-grams to be extracted. All values of n such that min_n <= n <= max_n.
        will be used.
    hashing : typing.Literal["fast", "murmur"], default=fast
        Hashing function. fast is faster but
        might have some concern with its entropy.
    minmax_hash : bool, default=False
        if True, return min hash and max hash concatenated.
    handle_missing : typing.Literal["error", "zero_impute"], default=zero_impute
        Whether to raise an error or encode missing values (NaN) with
        vectors filled with zeros.

    Attributes
    ----------
    hash_dict_ : LRUDict
        Computed hashes.
    
    Examples
    --------
    >>> enc = MinHashEncoder(n_components=5)

    Let's encode the following non-normalized data:

    >>> X = [['paris, FR'], ['Paris'], ['London, UK'], ['London']]

    >>> enc.fit(X)
    MinHashEncoder()

    The encoded data with 5 components are:

    >>> enc.transform(X)
    array([[-1.78337518e+09, -1.58827021e+09, -1.66359234e+09,
            -1.81988679e+09, -1.96259387e+09],
           [-8.48046971e+08, -1.76657887e+09, -1.55891205e+09,
            -1.48574446e+09, -1.68729890e+09],
           [-1.97582893e+09, -2.09500033e+09, -1.59652117e+09,
            -1.81759383e+09, -2.09569333e+09],
           [-1.97582893e+09, -2.09500033e+09, -1.53072052e+09,
            -1.45918266e+09, -1.58098831e+09]])

    References
    ----------
    For a detailed description of the method, see
    `Encoding high-cardinality string categorical variables
    <https://hal.inria.fr/hal-02171256v4>`_ by Cerda, Varoquaux (2019).

    """

    hash_dict_: LRUDict

    _capacity: int = 2**10

    def __init__(
        self,
        n_components: int = 30,
        ngram_range: Tuple[int, int] = (2, 4),
        hashing: Literal["fast", "murmur"] = "fast",
        minmax_hash: bool = False,
        handle_missing: Literal["error", "zero_impute"] = "zero_impute",
    ):
        self.ngram_range = ngram_range
        self.n_components = n_components
        self.hashing = hashing
        self.minmax_hash = minmax_hash
        self.handle_missing = handle_missing

    def _more_tags(self) -> Dict[str, List[str]]:
        """
        Used internally by sklearn to ease the estimator checks.
        """
        return {"X_types": ["categorical"]}

    def _get_murmur_hash(self, string: str) -> np.array:
        """
        Encode a string using murmur hashing function.

        Parameters
        ----------
        string : str
            The string to encode.
        n_components : int
            The number of dimension of encoded string.
        ngram_range : typing.Tuple[int, int]
            The lower and upper boundaries of the range of n-values for
            different n-grams to be extracted.
            All values of n such that min_n <= n <= max_n.

        Returns
        -------
        ndarray of shape (n_components, )
            The encoded string.
        """
        min_hashes = np.ones(self.n_components) * np.infty
        grams = get_unique_ngrams(string, self.ngram_range)
        if len(grams) == 0:
            grams = get_unique_ngrams(" Na ", self.ngram_range)
        for gram in grams:
            hash_array = np.array(
                [
                    murmurhash3_32("".join(gram), seed=d, positive=True)
                    for d in range(self.n_components)
                ]
            )
            min_hashes = np.minimum(min_hashes, hash_array)
        return min_hashes / (2**32 - 1)

    def _get_fast_hash(self, string: str) -> np.array:
        """
        Encode a string with fast hashing function.
        fast hashing supports both min_hash and minmax_hash encoding.

        Parameters
        ----------
        string : str
            The string to encode.

        Returns
        -------
        ndarray of shape (n_components, )
            The encoded string, using specified encoding scheme.
        """
        if self.minmax_hash:
            return np.concatenate(
                [
                    ngram_min_hash(string, self.ngram_range, seed, return_minmax=True)
                    for seed in range(self.n_components // 2)
                ]
            )
        else:
            return np.array(
                [
                    ngram_min_hash(string, self.ngram_range, seed)
                    for seed in range(self.n_components)
                ]
            )

    def fit(self, X, y=None) -> "MinHashEncoder":
        """
        Fit the MinHashEncoder to X. In practice, just initializes a dictionary
        to store encodings to speed up computation.

        Parameters
        ----------
        X : array-like, shape (n_samples, ) or (n_samples, 1)
            The string data to encode.
        y : None
            Unused, only here for compatibility.

        Returns
        -------
        MinHashEncoder
            The fitted MinHashEncoder instance.
        """
        if self.hashing not in ["fast", "murmur"]:
            raise ValueError(
                f"Got hashing={self.hashing!r}, "
                'but expected any of {"fast", "murmur"}. '
            )
        if self.handle_missing not in ["error", "zero_impute"]:
            raise ValueError(
                f"Got handle_missing={self.handle_missing!r}, but expected "
                'any of {"error", "zero_impute"}. '
            )
        self.count = 0
        self.hash_dict_ = LRUDict(capacity=self._capacity)
        return self

    def transform(self, X) -> np.array:
        """
        Transform X using specified encoding scheme.

        Parameters
        ----------
        X : array-like, shape (n_samples, ) or (n_samples, 1)
            The string data to encode.

        Returns
        -------
        ndarray of shape (n_samples, n_components)
            Transformed input.
        """
        X = check_input(X)
        if self.minmax_hash:
            assert (
                self.n_components % 2 == 0
            ), "n_components should be even when minmax_hash=True. "
        if self.hashing == "murmur":
            assert (
                not self.minmax_hash
            ), 'minmax_hash is not implemented with hashing="murmur". '

        # TODO: Parallelize
        is_nan_idx = False

        if self.hashing == "fast":
            X_out = np.zeros((len(X[:]), self.n_components * X.shape[1]))
            counter = self.n_components
            for k in range(X.shape[1]):
                X_in = X[:, k].reshape(-1)
                for i, x in enumerate(X_in):
                    if (
                        isinstance(x, float)  # true if x is a missing value
                        or x is None
                    ):
                        is_nan_idx = True
                    elif len(x) == 0:
                        is_nan_idx = True
                    elif x not in self.hash_dict_:
                        X_out[i, k * self.n_components : counter] = self.hash_dict_[
                            x
                        ] = self._get_fast_hash(x)
                    else:
                        X_out[i, k * self.n_components : counter] = self.hash_dict_[x]
                counter += self.n_components
        if self.hashing == "murmur":
            X_out = np.zeros((len(X[:]), self.n_components * X.shape[1]))
            counter = self.n_components
            for k in range(X.shape[1]):
                X_in = X[:, k].reshape(-1)
                for i, x in enumerate(X_in):
                    if isinstance(x, float) or x is None:
                        is_nan_idx = True
                    elif len(x) == 0:
                        is_nan_idx = True
                    elif x not in self.hash_dict_:
                        X_out[i, k * self.n_components : counter] = self.hash_dict_[
                            x
                        ] = self._get_murmur_hash(x)
                    else:
                        X_out[i, k * self.n_components : counter] = self.hash_dict_[x]
                counter += self.n_components

        if is_nan_idx and self.handle_missing == "error":
            raise ValueError(
                "Found missing values in input data; set "
                "handle_missing='zero_impute' "
                "to encode with missing values. "
            )
        return X_out
