# Test image: PostgreSQL 16 with MusicBrainz's custom collation/unaccent extensions
# built in. Used by the integration test suite via testcontainers.

FROM postgres:16

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates build-essential postgresql-server-dev-16 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --depth=1 https://github.com/metabrainz/musicbrainz-server.git .

RUN cd postgresql-extensions \
    && make \
    && make install

# Clean up the build deps and source to keep the image small.
RUN apt-get purge -y --auto-remove build-essential postgresql-server-dev-16 git \
    && rm -rf /src
