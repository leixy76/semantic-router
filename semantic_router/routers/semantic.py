from typing import Any, List, Optional

import numpy as np

from semantic_router.encoders import DenseEncoder
from semantic_router.index.base import BaseIndex
from semantic_router.llms import BaseLLM
from semantic_router.route import Route
from semantic_router.routers.base import BaseRouter
from semantic_router.utils.logger import logger


class SemanticRouter(BaseRouter):
    """A router that uses a dense encoder to encode routes and utterances."""

    def __init__(
        self,
        encoder: Optional[DenseEncoder] = None,
        llm: Optional[BaseLLM] = None,
        routes: Optional[List[Route]] = None,
        index: Optional[BaseIndex] = None,  # type: ignore
        top_k: int = 5,
        aggregation: str = "mean",
        auto_sync: Optional[str] = None,
    ):
        index = self._get_index(index=index)
        encoder = self._get_encoder(encoder=encoder)
        super().__init__(
            encoder=encoder,
            llm=llm,
            routes=routes if routes else [],
            index=index,
            top_k=top_k,
            aggregation=aggregation,
            auto_sync=auto_sync,
        )

    def _encode(self, text: list[str]) -> Any:
        """Given some text, encode it.

        :param text: The text to encode.
        :type text: list[str]
        :return: The encoded text.
        :rtype: Any
        """
        # create query vector
        xq = np.array(self.encoder(text))
        return xq

    async def _async_encode(self, text: list[str]) -> Any:
        """Given some text, encode it.

        :param text: The text to encode.
        :type text: list[str]
        :return: The encoded text.
        :rtype: Any
        """
        # create query vector
        xq = np.array(await self.encoder.acall(docs=text))
        return xq

    def add(self, routes: List[Route] | Route):
        """Add a route to the local SemanticRouter and index.

        :param route: The route to add.
        :type route: Route
        """
        current_local_hash = self._get_hash()
        current_remote_hash = self.index._read_hash()
        if current_remote_hash.value == "":
            # if remote hash is empty, the index is to be initialized
            current_remote_hash = current_local_hash
        if isinstance(routes, Route):
            routes = [routes]
        # create embeddings for all routes
        route_names, all_utterances, all_function_schemas, all_metadata = (
            self._extract_routes_details(routes, include_metadata=True)
        )
        dense_emb = self._encode(all_utterances)
        self.index.add(
            embeddings=dense_emb.tolist(),
            routes=route_names,
            utterances=all_utterances,
            function_schemas=all_function_schemas,
            metadata_list=all_metadata,
        )

        self.routes.extend(routes)
        if current_local_hash.value == current_remote_hash.value:
            self._write_hash()  # update current hash in index
        else:
            logger.warning(
                "Local and remote route layers were not aligned. Remote hash "
                f"not updated. Use `{self.__class__.__name__}.get_utterance_diff()` "
                "to see details."
            )
