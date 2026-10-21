# ShopKart's Postgres with the seed already loaded, so a sandbox's database starts in a
# second instead of initialising and seeding 370k rows on every boot.
#
# Stage 1 runs the official entrypoint's first-boot initialisation at build time (init.sql
# included), with its final `exec postgres` disabled. Stage 2 is a clean image with that data
# directory. PGDATA lives outside the image's declared VOLUME, so the driver's tmpfs on
# /var/lib/postgresql doesn't hide it; writes during play go to the container's own layer.
#
# The superuser is `postgres`, with a random password generated here and thrown away: the
# platform uses this container's local socket. The app and the player get the non-superuser
# `shopkart` role (init.sql, ADR 015).
FROM postgres:18-alpine AS seed
ENV PGDATA=/srv/pgdata POSTGRES_USER=postgres POSTGRES_DB=shopkart
COPY init.sql /docker-entrypoint-initdb.d/init.sql
RUN sed -i 's/^\texec "\$@"$/\techo "seeded"/' /usr/local/bin/docker-entrypoint.sh \
    && grep -q 'echo "seeded"' /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p "$PGDATA" && chown postgres:postgres "$PGDATA" \
    && POSTGRES_PASSWORD="$(head -c 32 /dev/urandom | base64)" docker-entrypoint.sh postgres

FROM postgres:18-alpine
ENV PGDATA=/srv/pgdata
COPY --from=seed --chown=postgres:postgres /srv/pgdata /srv/pgdata
