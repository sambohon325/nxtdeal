"""Read-only NXTDeal release smoke checks. Never bypass TLS or send credentials."""
import concurrent.futures
import json
import socket
import ssl
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe(host, path='/', origin=None):
    result = {'host':host,'path':path,'origin':origin,'ready':False}
    try:
        result['addresses'] = sorted({entry[4][0] for entry in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)})
    except OSError:
        return {**result,'error':'dns_failed'}
    headers = {'User-Agent':'NXTDeal-release-check/1'}
    if origin:
        headers.update({'Origin':origin,'Access-Control-Request-Method':'POST',
                        'Access-Control-Request-Headers':'authorization,content-type'})
    request = urllib.request.Request('https://' + host + path,headers=headers,method='OPTIONS' if origin else 'GET')
    opener = urllib.request.build_opener(NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    try:
        try:
            response = opener.open(request,timeout=12)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            result['status'] = response.code
            result['tls_verified'] = True
            if origin:
                result['origin_allowed'] = response.headers.get('Access-Control-Allow-Origin') == origin
                result['credentials_allowed'] = response.headers.get('Access-Control-Allow-Credentials') == 'true'
                allowed_headers = {item.strip().lower() for item in response.headers.get('Access-Control-Allow-Headers','').split(',')}
                result['headers_allowed'] = {'authorization','content-type'} <= allowed_headers
                result['ready'] = response.code == 200 and all(result[key] for key in ('origin_allowed','credentials_allowed','headers_allowed'))
            else:
                # Availability is only a smoke check, not proof of login/workflow success.
                result['ready'] = response.code == 200
                result['content_type'] = response.headers.get_content_type()
    except (urllib.error.URLError,ssl.SSLError,OSError):
        result['error'] = 'tls_or_connection_failed'
    return result


def main():
    checks = [('nxtdeal.app','/',None),('www.nxtdeal.app','/',None),
              ('app.nxtdeal.app','/',None),('app.nxtdeal.app','/workspace',None)]
    checks += [('api.nxtdeal.app','/auth/login',origin) for origin in
               ('https://nxtdeal.app','https://www.nxtdeal.app','https://app.nxtdeal.app')]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda item:probe(*item),checks))
    print(json.dumps({'scope':'unauthenticated_release_smoke','checks':results,
                      'ready':all(item['ready'] for item in results)},indent=2))
    return 0 if all(item['ready'] for item in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
