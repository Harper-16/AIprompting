# main.py
from io import BytesIO
import base64
import requests
import streamlit as st
from PIL import Image

import config

IMAGE_MODEL = "@cf/black-forest-labs/flux-1-schnell"
IMAGE_API_URL = "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/" + IMAGE_MODEL
FILTER_API_URL = "https://filters-zeta.vercel.app/api/filter"

ENHANCE_SYS = (
    "Improve prompts for text-to-image. Return ONLY the enhanced prompt. "
    "Add subject, style, lighting, camera angle, background, colors. Keep it safe."
)

def check_prompt_with_filter_api(prompt: str):
    try:
        response = requests.post(
            FILTER_API_URL,
            json={"prompt": prompt},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, dict):
            return {"ok": False, "reason": "Invalid filter API response."}

        return data

    except Exception as e:
        return {
            "ok": False,
            "reason": f"Filter API error: {str(e)}",
        }


def enhance_prompt(raw: str) -> str:
    from groq import generate_response

    out = generate_response(
        f"{ENHANCE_SYS}\nUser prompt: {raw}",
        temperature=0.4,
        max_tokens=220,
    )
    return (out or raw).strip()


def gen_image(prompt: str, account_id: str, api_token: str):
    filter_result = check_prompt_with_filter_api(prompt)
    if not filter_result.get("ok"):
        return None, f" Prompt blocked by safety filter. {filter_result.get('reason', 'Unsafe prompt')}"

    if not account_id or not api_token:
        return (
            None,
            "Enter your Cloudflare account ID and Workers AI API token above. "
            "Create a token with Workers AI Read and Edit permissions in the "
            "[Cloudflare dashboard](https://dash.cloudflare.com/?to=/:account/ai/workers-ai).",
        )

    url = IMAGE_API_URL.format(account_id=account_id)
    try:
        response = requests.post(
            url,
            headers={"Authorization": "Bearer " + api_token.strip()},
            json={"prompt": prompt, "steps": 4},
            timeout=(10, 180),
        )
        try:
            data = response.json()
        except ValueError:
            data = {}

        if not isinstance(data, dict):
            return None, "Cloudflare returned an invalid response."

        if not response.ok or not data.get("success", False):
            errors = data.get("errors", [])
            details = "; ".join(
                error.get("message", str(error)) if isinstance(error, dict) else str(error)
                for error in errors
            )
            if response.status_code in (401, 403) or "authentication error" in details.casefold():
                return (
                    None,
                    "Cloudflare rejected the API token. Verify your Cloudflare email, "
                    "successfully create a new Workers AI token with Read and Edit "
                    "permissions, and paste the full token value (not its name). "
                    "Make sure the account ID belongs to the same account. "
                    f"Cloudflare response: {details or f'HTTP {response.status_code}'}",
                )
            if not details:
                details = response.text[:500] or f"HTTP {response.status_code}"
            return None, f"Cloudflare image generation failed: {details}"

        result = data.get("result")
        if not isinstance(result, dict):
            return None, "Cloudflare returned a response without an image."

        image_b64 = result.get("image")
        if not isinstance(image_b64, str):
            return None, "Cloudflare returned a response without an image."

        try:
            with Image.open(BytesIO(base64.b64decode(image_b64, validate=True))) as image:
                return image.copy(), None
        except (ValueError, OSError) as error:
            return None, f"Cloudflare returned invalid image data: {error}"
    except requests.RequestException as error:
        return None, f"Could not reach Cloudflare image generation: {error}"


def main():
    st.set_page_config(page_title="Safe AI Image Generator", layout="centered")
    st.title(" Safe AI Image Generator")
    st.info(
        "Flow: Enter a prompt → enhance it → check it using the deployed safety API "
        "→ generate with Cloudflare Workers AI (10,000 free Neurons per day)."
    )

    with st.form("image_form"):
        raw = st.text_area(
            "Image Description",
            height=120,
            placeholder="Example: A cozy cabin in snowy mountains at sunrise, cinematic lighting",
        )
        account_id = config.CLOUDFLARE_ACCOUNT_ID or st.text_input(
            "Cloudflare Account ID",
            help="Find this in the Cloudflare dashboard under Workers AI.",
        )
        api_token = config.CLOUDFLARE_API_TOKEN or st.text_input(
            "Cloudflare Workers AI API Token",
            type="password",
            help="Requires Workers AI Read and Edit permissions.",
        )
        submit = st.form_submit_button("Generate Image")

    if submit:
        raw = raw.strip()

        if not raw:
            st.warning(" Please enter an image description.")
            return

        if not account_id or not api_token:
            st.error(
                "Enter your Cloudflare account ID and Workers AI API token above. "
                "Create a token with Workers AI Read and Edit permissions in the "
                "[Cloudflare dashboard](https://dash.cloudflare.com/?to=/:account/ai/workers-ai)."
            )
            return

        raw_check = check_prompt_with_filter_api(raw)
        if not raw_check.get("ok"):
            st.error(f" Prompt blocked. {raw_check.get('reason', 'Unsafe prompt')}")
            return

        with st.spinner("Enhancing your prompt..."):
            final_prompt = enhance_prompt(raw)

        enhanced_check = check_prompt_with_filter_api(final_prompt)
        if not enhanced_check.get("ok"):
            st.error(f" Enhanced prompt blocked. {enhanced_check.get('reason', 'Unsafe prompt')}")
            return

        st.markdown("#### Enhanced Prompt")
        st.code(final_prompt)

        with st.spinner("Generating image..."):
            img, err = gen_image(final_prompt, account_id, api_token)

        if err:
            st.error(err)
            return

        st.image(img, caption="Generated Image", use_container_width=True)
        st.session_state.generated_image = img

    img = st.session_state.get("generated_image")
    if img:
        buf = BytesIO()
        img.save(buf, format="PNG")
        st.download_button(
            " Download Image",
            buf.getvalue(),
            "ai_generated_image.png",
            "image/png",
        )


if __name__ == "__main__":
    main()