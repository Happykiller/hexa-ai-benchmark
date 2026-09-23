"""Benchmark « Blender 3D » : un agent modélise, rigge et anime une créature d'après une
planche concept ; l'auditeur rejoue son build.py dans Blender et note le résultat.

Autonome vis-à-vis du benchmark Todo List : seul le noyau auditor/engine est partagé.
Importer ce paquet rend `engine` importable (voir _bootstrap), avant tout sous-module.
"""

from blender_bench import _bootstrap  # noqa: F401
