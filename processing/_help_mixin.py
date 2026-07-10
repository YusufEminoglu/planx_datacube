# -*- coding: utf-8 -*-
"""Shared helpUrl() mixin for all DataCube Processing algorithms."""


class DataCubeHelpMixin:
    """Mixin that provides helpUrl() pointing to the DataCube README tool list."""

    _HELP_BASE = "https://github.com/YusufEminoglu/planx_datacube"

    def helpUrl(self) -> str:
        return self._HELP_BASE
