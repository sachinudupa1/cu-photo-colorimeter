"""cucolor: estimate Cu(II)-ammonia concentration from a phone photo.

Modules
    features     photo -> colour numbers -> camera absorbance
    calibration  straight-line calibration, detection limit, prediction interval
    pipeline     manifest CSV -> per-solution features
    agent        step-by-step agent: quality checks -> measure -> range check -> report
    synth        synthetic photo generator (for testing without a lab)
"""

__version__ = "0.1.0"
