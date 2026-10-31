FROM nginx:stable-alpine
ARG SOURCE_COMMIT=unknown
LABEL org.opencontainers.image.revision=$SOURCE_COMMIT \
      org.opencontainers.image.source="https://github.com/sambohon325/dealerOS"
COPY deploy/synthetic/nginx.conf /etc/nginx/nginx.conf
USER 101:101
ENTRYPOINT []
CMD ["nginx", "-g", "daemon off;"]
