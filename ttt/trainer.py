"""Train solver-judge using the Python API.

Usage:
    python -m ttt.trainer +task_yaml=path/to/task.yaml

With Hydra overrides:
    python -m ttt.trainer +task_yaml=path/to/task.yaml model.name=Qwen/Qwen3-1.7B +repeat=5000
"""

import yaml
import hydra
from ttt.evaluator import evaluator
from omegaconf import DictConfig
import ttt.generator as gen_module
from ttt.generator import generator

from rllm.data.dataset import Dataset
from rllm.experimental.unified_trainer import AgentTrainer


@hydra.main(config_path="pkg://rllm.experimental.config", config_name="unified", version_base=None)
def main(config: DictConfig):
    task_yaml = config.get("task_yaml", None)
    if task_yaml is None:
        raise ValueError("task_yaml must be specified, e.g.: +task_yaml=path/to/task.yaml")

    with open(task_yaml) as f:
        task_config = yaml.safe_load(f)

    task_data = task_config.get("task", task_config)
    repeat = int(config.get("repeat", 1000))

    train_dataset = Dataset(data=[task_data] * repeat, name="task", split="train")
    test_dataset = Dataset(data=[task_data] * max(1, repeat // 10), name="task", split="test")

    if config.get("rllm", {}).get("trainer", {}).get("total_epochs") is None:
        config.rllm.trainer.total_epochs = 9999
    if config.get("data", {}).get("train_batch_size") is None:
        config.data.train_batch_size = 1
    if config.get("data", {}).get("val_batch_size") is None:
        config.data.val_batch_size = 1

    # Wire up the task_yaml path so the generator can find it
    gen_module._coral_state["task_yaml"] = str(task_yaml)

    trainer = AgentTrainer(
        backend="tinker",
        agent_flow=generator,
        evaluator=evaluator,
        config=config,
        train_dataset=train_dataset,
        val_dataset=test_dataset,
    )
    trainer.train()


if __name__ == "__main__":
    main()