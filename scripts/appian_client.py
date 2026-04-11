import time
import requests
import config

class AppianClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({"Appian-API-Key": api_key, "Accept": "application/json"})
        if config.PROXIES:
            self.session.proxies.update(config.PROXIES)

    def list_applications(self):
        return self._get(f"{self.base_url}/suite/api/v1/applications").json()

    def export_package(self, app_uuid):
        url = f"{self.base_url}/suite/api/v1/applications/{app_uuid}/export"
        resp = self._post(url, json={})
        if resp.headers.get("Content-Type","").startswith("application/zip"):
            return resp.content
        body = resp.json()
        dl_url = body.get("downloadUrl") or body.get("url")
        if dl_url:
            return self._get(dl_url, stream=True).content
        raise RuntimeError(f"Unexpected export response: {resp.text[:500]}")

    def inspect_package(self, package_bytes):
        url = f"{self.base_url}/suite/deployment-management/v2/inspections"
        resp = self._post_file(url, "package.zip", package_bytes)
        result = resp.json()
        uuid = result.get("uuid")
        if uuid:
            result = self._poll_status(f"{url}/{uuid}", {"COMPLETED","FAILED"})
        return result

    def deploy_package(self, package_bytes, name="Automated Deployment", description=""):
        url = f"{self.base_url}/suite/deployment-management/v2/deployments"
        resp = self.session.post(
            url,
            files={"zipFile": ("package.zip", package_bytes, "application/zip")},
            data={"json": f'{{"name":"{name}","description":"{description}","dataSource":"ADMIN"}}'},
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        result = resp.json()
        uuid = result.get("uuid")
        if uuid:
            result = self._poll_status(f"{url}/{uuid}", {"COMPLETED","FAILED"})
        return result

    def get_deployment_status(self, uuid):
        return self._get(f"{self.base_url}/suite/deployment-management/v2/deployments/{uuid}").json()

    def get_deployment_log(self, uuid):
        return self._get(f"{self.base_url}/suite/deployment-management/v2/deployments/{uuid}/log").json()

    def _get(self, url, **kw):
        kw.setdefault("timeout", config.REQUEST_TIMEOUT)
        r = self.session.get(url, **kw); r.raise_for_status(); return r

    def _post(self, url, **kw):
        kw.setdefault("timeout", config.REQUEST_TIMEOUT)
        r = self.session.post(url, **kw); r.raise_for_status(); return r

    def _post_file(self, url, filename, data):
        r = self.session.post(url, files={"zipFile":(filename,data,"application/zip")}, timeout=config.REQUEST_TIMEOUT)
        r.raise_for_status(); return r

    def _poll_status(self, url, terminal):
        deadline = time.time() + config.DEPLOY_POLL_TIMEOUT
        while time.time() < deadline:
            body = self._get(url).json()
            status = body.get("status","UNKNOWN")
            print(f"  ... status: {status}")
            if status in terminal: return body
            time.sleep(config.DEPLOY_POLL_INTERVAL)
        raise TimeoutError(f"Timed out after {config.DEPLOY_POLL_TIMEOUT}s")
