FROM pgvector/pgvector:pg16

COPY db/migrations/ /docker-entrypoint-initdb.d/
