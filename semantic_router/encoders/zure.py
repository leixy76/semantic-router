import os
from asyncio import sleep as asleep
from time import sleep
from typing import List, Optional, Union

import openai
from openai import OpenAIError
from openai._types import NotGiven
from openai.types import CreateEmbeddingResponse

from semantic_router.encoders import DenseEncoder
from semantic_router.utils.defaults import EncoderDefault
from semantic_router.utils.logger import logger


class AzureOpenAIEncoder(DenseEncoder):
    """Encoder for Azure OpenAI API.

    This class provides functionality to encode text documents using the Azure OpenAI API.
    It supports customization of the score threshold for filtering or processing the embeddings.
    """

    client: Optional[openai.AzureOpenAI] = None
    async_client: Optional[openai.AsyncAzureOpenAI] = None
    dimensions: Union[int, NotGiven] = NotGiven()
    type: str = "azure"
    api_key: Optional[str] = None
    deployment_name: Optional[str] = None
    azure_endpoint: Optional[str] = None
    api_version: Optional[str] = None
    model: Optional[str] = None
    max_retries: int = 3

    def __init__(
        self,
        api_key: Optional[str] = None,
        deployment_name: Optional[str] = None,
        azure_endpoint: Optional[str] = None,
        api_version: Optional[str] = None,
        model: Optional[str] = None,  # TODO we should change to `name` JB
        score_threshold: float = 0.82,
        dimensions: Union[int, NotGiven] = NotGiven(),
        max_retries: int = 3,
    ):
        """Initialize the AzureOpenAIEncoder.

        :param api_key: The API key for the Azure OpenAI API.
        :type api_key: str
        :param deployment_name: The name of the deployment to use.
        :type deployment_name: str
        :param azure_endpoint: The endpoint for the Azure OpenAI API.
        :type azure_endpoint: str
        :param api_version: The version of the API to use.
        :type api_version: str
        :param model: The model to use.
        :type model: str
        :param score_threshold: The score threshold for the embeddings.
        :type score_threshold: float
        :param dimensions: The dimensions of the embeddings.
        :type dimensions: int
        :param max_retries: The maximum number of retries for the API call.
        :type max_retries: int
        """
        name = deployment_name
        if name is None:
            name = EncoderDefault.AZURE.value["embedding_model"]
        super().__init__(name=name, score_threshold=score_threshold)
        self.api_key = api_key
        self.deployment_name = deployment_name
        self.azure_endpoint = azure_endpoint
        self.api_version = api_version
        self.model = model
        # set dimensions to support openai embed 3 dimensions param
        self.dimensions = dimensions
        if self.api_key is None:
            self.api_key = os.getenv("AZURE_OPENAI_API_KEY")
            if self.api_key is None:
                raise ValueError("No Azure OpenAI API key provided.")
        if max_retries is not None:
            self.max_retries = max_retries
        if self.deployment_name is None:
            self.deployment_name = EncoderDefault.AZURE.value["deployment_name"]
        # deployment_name may still be None, but it is optional in the API
        if self.azure_endpoint is None:
            self.azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            if self.azure_endpoint is None:
                raise ValueError("No Azure OpenAI endpoint provided.")
        if self.api_version is None:
            self.api_version = os.getenv("AZURE_OPENAI_API_VERSION")
            if self.api_version is None:
                raise ValueError("No Azure OpenAI API version provided.")
        if self.model is None:
            self.model = os.getenv("AZURE_OPENAI_MODEL")
            if self.model is None:
                raise ValueError("No Azure OpenAI model provided.")
        assert (
            self.api_key is not None
            and self.azure_endpoint is not None
            and self.api_version is not None
            and self.model is not None
        )

        try:
            self.client = openai.AzureOpenAI(
                azure_deployment=(
                    str(self.deployment_name) if self.deployment_name else None
                ),
                api_key=str(self.api_key),
                azure_endpoint=str(self.azure_endpoint),
                api_version=str(self.api_version),
            )
            self.async_client = openai.AsyncAzureOpenAI(
                azure_deployment=(
                    str(self.deployment_name) if self.deployment_name else None
                ),
                api_key=str(self.api_key),
                azure_endpoint=str(self.azure_endpoint),
                api_version=str(self.api_version),
            )
        except Exception as e:
            raise ValueError(
                f"OpenAI API client failed to initialize. Error: {e}"
            ) from e

    def __call__(self, docs: List[str]) -> List[List[float]]:
        """Encode a list of documents into embeddings using the Azure OpenAI API.

        :param docs: The documents to encode.
        :type docs: List[str]
        :return: The embeddings for the documents.
        :rtype: List[List[float]]
        """
        if self.client is None:
            raise ValueError("Azure OpenAI client is not initialized.")
        embeds = None

        # Exponential backoff
        for j in range(self.max_retries + 1):
            try:
                embeds = self.client.embeddings.create(
                    input=docs,
                    model=str(self.model),
                    dimensions=self.dimensions,
                )
                if embeds.data:
                    break
            except OpenAIError as e:
                logger.error("Exception occurred", exc_info=True)
                if self.max_retries != 0 and j < self.max_retries:
                    sleep(2**j)
                    logger.warning(
                        f"Retrying in {2**j} seconds due to OpenAIError: {e}"
                    )
                else:
                    raise
            except Exception as e:
                logger.error(f"Azure OpenAI API call failed. Error: {e}")
                raise ValueError(f"Azure OpenAI API call failed. Error: {e}") from e

        if (
            not embeds
            or not isinstance(embeds, CreateEmbeddingResponse)
            or not embeds.data
        ):
            raise ValueError("No embeddings returned.")

        embeddings = [embeds_obj.embedding for embeds_obj in embeds.data]
        return embeddings

    async def acall(self, docs: List[str]) -> List[List[float]]:
        """Encode a list of documents into embeddings using the Azure OpenAI API asynchronously.

        :param docs: The documents to encode.
        :type docs: List[str]
        :return: The embeddings for the documents.
        :rtype: List[List[float]]
        """
        if self.async_client is None:
            raise ValueError("Azure OpenAI async client is not initialized.")
        embeds = None
        # Exponential backoff
        for j in range(self.max_retries + 1):
            try:
                embeds = await self.async_client.embeddings.create(
                    input=docs,
                    model=str(self.model),
                    dimensions=self.dimensions,
                )
                if embeds.data:
                    break

            except OpenAIError as e:
                logger.error("Exception occurred", exc_info=True)
                if self.max_retries != 0 and j < self.max_retries:
                    await asleep(2**j)
                    logger.warning(
                        f"Retrying in {2**j} seconds due to OpenAIError: {e}"
                    )
                else:
                    raise
            except Exception as e:
                logger.error(f"Azure OpenAI API call failed. Error: {e}")
                raise ValueError(f"Azure OpenAI API call failed. Error: {e}") from e

        if (
            not embeds
            or not isinstance(embeds, CreateEmbeddingResponse)
            or not embeds.data
        ):
            raise ValueError("No embeddings returned.")

        embeddings = [embeds_obj.embedding for embeds_obj in embeds.data]
        return embeddings
