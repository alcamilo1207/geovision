import os
import uvicorn
import webbrowser
import threading
import time
import sys

def open_browser(port):
    time.sleep(1.2)
    url = f"http://localhost:{port}"
    print(f"\n🌐 Abriendo navegador en {url} ...\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    is_cloud = os.environ.get("PORT") is not None or os.environ.get("RENDER") is not None or os.environ.get("RAILWAY_ENVIRONMENT") is not None

    print("=" * 70)
    print("🏭 Iniciando GeoVision Plant Extractor — Versión React (U044)")
    print("⚡ Backend: FastAPI + Uvicorn")
    print("📐 GIS GeoTIFF, API 581, OpenSRANE, Cozzani Probit & QRA Standards")
    print(f"🌐 Puerto: {port} {'(Cloud / Nube)' if is_cloud else '(Local)'}")
    print("=" * 70)

    if not is_cloud:
        threading.Thread(target=open_browser, args=(port,), daemon=True).start()

    uvicorn.run("api_app:app", host="0.0.0.0", port=port, reload=not is_cloud)

