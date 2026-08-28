import json
import re
from urllib.parse import urlparse

import requests
from flask import Flask, render_template, request

app = Flask(__name__)

REQUEST_TIMEOUT = 15


def normalize_base_url(raw_url):
    url = raw_url.strip().rstrip("/")
    if not url:
        raise ValueError("端點網址不可為空")
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    if not re.search(r"/v1$", url, re.IGNORECASE):
        url += "/v1"
    return url


def slugify(value, fallback="custom"):
    slug = re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower()).strip("-")
    return slug or fallback


def default_provider_id(base_url):
    host = urlparse(base_url).hostname or "custom-provider"
    return slugify(host)


def fetch_models(base_url, api_key):
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    resp = requests.get(f"{base_url}/models", headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()

    if isinstance(payload, dict):
        raw_models = payload.get("data", [])
    elif isinstance(payload, list):
        raw_models = payload
    else:
        raw_models = []

    model_ids = []
    for item in raw_models:
        if isinstance(item, dict):
            model_id = item.get("id")
        else:
            model_id = item
        if model_id:
            model_ids.append(str(model_id))
    return model_ids


def build_opencode_jsonc(provider_id, provider_name, base_url, api_key, model_ids):
    models = {model_id: {"name": model_id} for model_id in sorted(model_ids)}

    provider_entry = {
        "npm": "@ai-sdk/openai-compatible",
        "name": provider_name,
        "options": {
            "baseURL": base_url,
        },
        "models": models,
    }

    if api_key:
        provider_entry["options"]["apiKey"] = api_key

    config = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            provider_id: provider_entry,
        },
    }

    return json.dumps(config, indent=2, ensure_ascii=False)


@app.route("/", methods=["GET", "POST"])
def index():
    form_values = {
        "endpoint": "",
        "api_key": "",
        "provider_id": "",
        "provider_name": "",
    }
    error = None
    result = None
    model_count = 0

    if request.method == "POST":
        form_values["endpoint"] = request.form.get("endpoint", "")
        form_values["api_key"] = request.form.get("api_key", "")
        form_values["provider_id"] = request.form.get("provider_id", "")
        form_values["provider_name"] = request.form.get("provider_name", "")

        try:
            base_url = normalize_base_url(form_values["endpoint"])
            provider_id = slugify(form_values["provider_id"]) if form_values["provider_id"] else default_provider_id(base_url)
            provider_name = form_values["provider_name"].strip() or provider_id

            model_ids = fetch_models(base_url, form_values["api_key"].strip())
            if not model_ids:
                error = "該端點回傳的 /v1/models 沒有任何模型資料"
            else:
                result = build_opencode_jsonc(
                    provider_id,
                    provider_name,
                    base_url,
                    form_values["api_key"].strip(),
                    model_ids,
                )
                model_count = len(model_ids)
        except ValueError as exc:
            error = str(exc)
        except requests.exceptions.Timeout:
            error = "連線逾時，請確認端點網址是否正確且可連線"
        except requests.exceptions.ConnectionError:
            error = "無法連線到該端點，請確認網址是否正確"
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            error = f"呼叫 /v1/models 失敗，HTTP 狀態碼 {status}"
        except json.JSONDecodeError:
            error = "端點回傳的內容不是有效的 JSON"
        except requests.exceptions.RequestException as exc:
            error = f"請求發生錯誤: {exc}"

    return render_template(
        "index.html",
        form_values=form_values,
        error=error,
        result=result,
        model_count=model_count,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
