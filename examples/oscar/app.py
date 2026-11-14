"""Run upstream shop commands or serve it with standard Django/SQLite OTel instrumentation."""

import os
import secrets
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "data/external/django-oscar/sandbox"))
os.environ["DJANGO_SETTINGS_MODULE"] = "examples.oscar.settings"
os.environ.setdefault("OSCAR_LOCAL_SECRET", secrets.token_urlsafe(48))


def main():
    import django

    command = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if command == "serve":
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.django import DjangoInstrumentor
        from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": "oscar-shop"}))
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint="http://127.0.0.1:8100/v1/traces", timeout=5),
                schedule_delay_millis=100,
            )
        )
        trace.set_tracer_provider(provider)
        SQLite3Instrumentor().instrument()
        DjangoInstrumentor().instrument(excluded_urls="static/.*,favicon.ico")
        django.setup()
        import uvicorn
        from django.core.asgi import get_asgi_application

        try:
            uvicorn.run(get_asgi_application(), host="127.0.0.1", port=8200, log_level="warning")
        finally:
            provider.shutdown()
        return
    django.setup()
    from django.core.management import call_command

    if command == "setup":
        call_command("migrate", interactive=False, verbosity=0)
        media = ROOT / "data/oscar-media"
        media.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(
            ROOT / "data/external/django-oscar/src/oscar/static_src/oscar/img/image_not_found.jpg",
            media / "image_not_found.jpg",
        )
        from django.contrib.sites.models import Site

        from oscar.core.loading import get_model

        ProductClass = get_model("catalogue", "ProductClass")
        Product = get_model("catalogue", "Product")
        Partner = get_model("partner", "Partner")
        StockRecord = get_model("partner", "StockRecord")
        Site.objects.update_or_create(
            id=1, defaults={"domain": "127.0.0.1:8200", "name": "IncidentLab Oscar shop"}
        )
        product_class, _ = ProductClass.objects.get_or_create(
            name="Lab products", defaults={"requires_shipping": False, "track_stock": True}
        )
        partner, _ = Partner.objects.get_or_create(
            code="incidentlab", defaults={"name": "Local fixture supplier"}
        )
        for index in range(1, 13):
            product, _ = Product.objects.update_or_create(
                upc=f"IL-{index:03}",
                defaults={
                    "title": f"Engineering Notebook {index:02}",
                    "product_class": product_class,
                    "description": "Locally generated test catalogue item. No real customer data.",
                },
            )
            StockRecord.objects.update_or_create(
                product=product,
                partner=partner,
                defaults={
                    "partner_sku": f"IL-{index:03}",
                    "price_currency": "GBP",
                    "price": "12.00",
                    "num_in_stock": 100,
                },
            )
        call_command("rebuild_index", interactive=False, verbosity=0)
        call_command("collectstatic", interactive=False, verbosity=0)
        print("Oscar sandbox ready: 12 products, real stock records, no user accounts created.")
    else:
        raise SystemExit(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
