from core.pipeline_metrics import (
    get_conversion_rate
)

pipeline = {

    "NEW": 5,

    "CONTACTED": 3,

    "SOLD": 2
}

rate = (
    get_conversion_rate(
        pipeline
    )
)

print(
    "Conversion Rate:"
)

print(
    f"{rate}%"
)