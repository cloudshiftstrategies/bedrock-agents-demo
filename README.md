# Bedrock Agent Application
Testing using bedrock, agents, knowledgebases etc to make an agent

# Considerations
1. This requires a pinecone api key. Get one from https://www.pinecone.io/

2. The pinecone api secret is stored in secrets manager secret. The first deployment will fail due to permissions error. 
    ```
    $ cdk deploy --require-approval never --no-rollback

    ...Resource handler returned message: "The knowledge base storage configuration provided is invalid... The vector database encountered an error while processing the request: Wrong API key...
    ```
    Update the secret with the value of the secret and retry

3. The pinecone secret must be formatted like {"apiKey": "PINECONE_SECRET"} or you'll get a storage validation error on knowledgebase
