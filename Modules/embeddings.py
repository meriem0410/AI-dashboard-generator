"""
Modules/embeddings.py

Turns text into vectors for the schema knowledge base.

  FastEmbedEmbedder  a small neural model (BAAI/bge-small-en-v1.5, 384
                     numbers per text, runs on the CPU through ONNX, about
                     70 MB, downloaded on first use). It understands that
                     "fuel" and "gas" are close.
  HashingEmbedder    no download, no model: words (and their singular form)
                     are hashed into a fixed-size vector. It only matches
                     shared words, so "fuel cost" finds fuel_purchases but
                     "gas" does not. Used for tests and as an automatic
                     fallback when the neural model cannot be loaded.

get_embedder(name) picks one: "fastembed", "hashing", or "auto" (default:
fastembed, falling back to hashing with a printed warning). The environment
variable EMBEDDER sets the default. Vectors are L2-normalised, so the inner
product is the cosine similarity.
"""
import hashlib
import os
import re
import zlib

import numpy as np

FASTEMBED_MODEL = "BAAI/bge-small-en-v1.5"


def _normalise(vectors):
    vectors = np.asarray(vectors, dtype="float32")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


# Words that carry no meaning for finding a table: question words, and the
# words every chunk of the knowledge base repeats ("table", "columns", ...).
_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "in", "on", "for", "by", "per", "to",
    "is", "are", "was", "were", "be", "what", "which", "who", "how", "many",
    "much", "each", "every", "all", "with", "from", "at", "as", "than", "that",
    "this", "these", "those", "it", "its", "our", "we", "show", "me", "give",
    "table", "column", "row", "related", "join", "value", "range", "dimension",
    "measure", "date", "one", "id", "kpi", "idea", "dataset",
}


class HashingEmbedder:
    name = "hashing"

    def __init__(self, dim=4096):
        self.dim = dim

    @staticmethod
    def _tokens(text):
        words = re.findall(r"[a-z0-9]+", str(text).lower().replace("_", " "))
        out = []
        for w in words:
            if w in _STOPWORDS or w.rstrip("s") in _STOPWORDS:
                continue
            out.append(w)
            if len(w) > 3 and w.endswith("ies"):
                out.append(w[:-3] + "y")
            elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
                out.append(w[:-1])
        return out

    def embed(self, texts):
        vectors = np.zeros((len(texts), self.dim), dtype="float32")
        for i, text in enumerate(texts):
            counts = {}
            for token in self._tokens(text):
                counts[token] = counts.get(token, 0) + 1
            for token, count in counts.items():
                raw = token.encode("utf-8")
                weight = (1.0 + np.log(count)) / 2.0
                # two independent hashes: one accidental collision between two
                # different words then has almost no effect
                vectors[i, zlib.crc32(raw) % self.dim] += weight
                vectors[i, int.from_bytes(hashlib.md5(raw).digest()[:4], "big") % self.dim] += weight
        return _normalise(vectors)


class FastEmbedEmbedder:
    name = "fastembed"

    def __init__(self, model_name=FASTEMBED_MODEL):
        from fastembed import TextEmbedding      # imported here: optional dependency
        self._model = TextEmbedding(model_name=model_name)
        self.dim = len(next(iter(self._model.embed(["dimension probe"]))))

    def embed(self, texts):
        return _normalise(list(self._model.embed(list(texts))))


def get_embedder(name=None):
    name = (name or os.getenv("EMBEDDER", "auto")).strip().lower()
    if name == "hashing":
        return HashingEmbedder()
    if name == "fastembed":
        return FastEmbedEmbedder()
    try:
        return FastEmbedEmbedder()
    except Exception as e:                       # offline, missing package, ...
        print(f"[embeddings] fastembed unavailable ({type(e).__name__}); "
              "using the hashing embedder instead.")
        return HashingEmbedder()
