"""Controlled ROM Corruptor.

A modular, deterministic, region-aware binary/ROM corruption framework.

The package is split into layers:

* :mod:`controlled_corruptor.core` -- the mutation engine, PRNG, region
  model, project/seed serialization and validation. Contains no
  game-specific logic.
* :mod:`controlled_corruptor.platforms` -- platform adapters (Generic, N64,
  ...) that understand headers, endianness, protected regions and checksums.
* :mod:`controlled_corruptor.profiles` -- loader + schema for external
  JSON/YAML game profiles.
* :mod:`controlled_corruptor.emulator` -- emulator launch abstraction.
* :mod:`controlled_corruptor.cli` -- command line interface.
* :mod:`controlled_corruptor.ui` -- optional PySide6 desktop UI.

Design principle -- keep three concepts separate:

    WHERE corruption occurs   -> regions
    WHAT the data represents  -> categories / data_type
    HOW the data is mutated   -> mutation strategies
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
