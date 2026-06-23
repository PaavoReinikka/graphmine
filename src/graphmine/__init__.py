"""graphmine — statistically significant relation mining for repos and graphs.

Pipeline: encoder (corpus -> transactions+item labels) -> mine (Kingfisher) ->
postprocess (dedupe, clique-collapse, cross-subsystem ranking) -> report
(JSON sidecar + markdown). graphify is one optional consumer, not a dependency.
"""
__version__ = "0.1.0"
