FROM python:3.10 AS builder

WORKDIR /usr/src/app

RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"

RUN pip install --upgrade pip

# Copy the generated package (source of the FastAPI server)
COPY generated/ .

# Copy the shared analyzer module into a known location
COPY app/ /usr/src/analyzer/

RUN pip install --no-cache-dir .


FROM python:3.10 AS test_runner
WORKDIR /tmp
COPY --from=builder /venv /venv
COPY --from=builder /usr/src/app/tests tests
# Make the shared analyzer importable
COPY --from=builder /usr/src/analyzer /usr/src/analyzer
ENV PATH=/venv/bin:$PATH
ENV ANALYZER_DIR=/usr/src/analyzer

# install test dependencies
RUN pip install pytest

# run tests
RUN pytest tests


FROM python:3.10 AS service
WORKDIR /root/app/site-packages
COPY --from=test_runner /venv /venv
COPY --from=builder /usr/src/analyzer /usr/src/analyzer
ENV PATH=/venv/bin:$PATH
ENV ANALYZER_DIR=/usr/src/analyzer
