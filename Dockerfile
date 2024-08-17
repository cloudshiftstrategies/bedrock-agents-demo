# https://www.fpgmaas.com/blog/aws-cdk-lambdas-docker
FROM public.ecr.aws/lambda/python:3.11-x86_64
ENV PYTHONUNBUFFERED=true

# Install poetry
ENV POETRY_VERSION=1.3.2
RUN pip install "poetry==$POETRY_VERSION"
RUN yum install -y git

# Install dependencies
WORKDIR ${LAMBDA_TASK_ROOT}
COPY poetry.lock pyproject.toml ${LAMBDA_TASK_ROOT}/
RUN poetry config virtualenvs.create false &&\
     poetry install --no-cache --no-interaction --no-ansi --no-root --only main

# Cleanup yum and pip caches
RUN yum remove -y git &&\
    yum -y clean all &&\
    rm -rf /var/cache &&\
    pip cache purge &&\
    poetry cache clear pypi --all

# Copy the lib dir to the Docker image
COPY cdk/ ${LAMBDA_TASK_ROOT}/cdk/

# Set the CMD to lambda handler (could also be done as a parameter override outside of the Dockerfile)
CMD ["lib.functions.some_file.handler"]