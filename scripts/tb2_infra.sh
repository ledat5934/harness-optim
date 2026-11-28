# Sourced by the TB2 wrappers. Infra only, identical for every arm:
# this sandbox re-terminates outbound TLS, so task containers (agent commands and the verifier, which
# downloads uv/pytest) must trust the sandbox CA. Mount it read-only and point the usual CA env vars at it.
CA_HOST=/root/.ccr/ca-bundle.crt
CA_CT=/usr/local/share/sandbox-proxy-ca.crt
CA_ENV_JSON="{\"SSL_CERT_FILE\":\"$CA_CT\",\"REQUESTS_CA_BUNDLE\":\"$CA_CT\",\"CURL_CA_BUNDLE\":\"$CA_CT\",\"PIP_CERT\":\"$CA_CT\",\"NODE_EXTRA_CA_CERTS\":\"$CA_CT\",\"GIT_SSL_CAINFO\":\"$CA_CT\"}"
TB2_INFRA_ARGS=(--mounts-json "[{\"type\":\"bind\",\"source\":\"$CA_HOST\",\"target\":\"$CA_CT\",\"read_only\":true}]"
  --ek "persistent_env=$CA_ENV_JSON")
for k in SSL_CERT_FILE REQUESTS_CA_BUNDLE CURL_CA_BUNDLE PIP_CERT NODE_EXTRA_CA_CERTS GIT_SSL_CAINFO; do
  TB2_INFRA_ARGS+=(--ve "$k=$CA_CT"); done
