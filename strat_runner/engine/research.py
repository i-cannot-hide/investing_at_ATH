from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from executors.mock_executor import MockExecutor
from engine.environment import Environment
from engine.experiment import Experiment
from engine.outcome_registry import allocate_research_id


@dataclass
class Research:
    """A named batch of experiments to run and compare together."""

    name: str
    experiments: list[Experiment]
    research_id: str | None = field(default=None, init=False, repr=False)

    def run(
        self,
        data_files: str | list[str],
        *,
        mock_executor=None,
        full_debug_outcomes: bool = False,
        interval: str = "1d",
        start_date: str | datetime | None = None,
        end_date: str | datetime | None = None,
        outcomes_dir: Path | str | None = None,
    ) -> str:
        """Run every experiment and tag outcomes with this research.

        Returns the `research_id` shared by all outcomes in this batch.
        """
        if not self.experiments:
            raise ValueError("Research must contain at least one experiment")

        self.research_id = allocate_research_id()
        executor = mock_executor if mock_executor is not None else MockExecutor()

        for experiment in self.experiments:
            Environment(
                experiment,
                executor,
                data_files,
                full_debug_outcomes=full_debug_outcomes,
                interval=interval,
                start_date=start_date,
                end_date=end_date,
                outcomes_dir=outcomes_dir,
                research_name=self.name,
                research_id=self.research_id,
            ).run()
            label = experiment.name or type(experiment.strategy).__name__
            print(f"Finished {self.name} / {label}")

        return self.research_id
