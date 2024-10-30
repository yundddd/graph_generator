import csv
import os

from pydantic import BaseModel


class DropPublishConfig(BaseModel):
    """
    This config describes which topic to drop and how many times.
    """

    topic: str
    drop: int


class MutatePublishConfig(BaseModel):
    """
    This config describes which topic to mutate and how many times.
    """

    topic: str
    value: int


class DropReceiveConfig(BaseModel):
    """
    This config describes which topic to drop received messages from and how many times.
    """

    topic: str
    drop: int


class DelayReceiveConfig(BaseModel):
    """
    This config describes which topic to delay a received message.
    It only delays a single instance.
    """

    topic: str
    delay: int


class DelayLoopConfig(BaseModel):
    """
    This config describes how long to delay a loop work. Subsequent loop work will also contain the same phase shift.
     For example if a node nominally execute periodic work as:
      t0        t1        t2        t3
       |_________|_________|_________|
    Delaying work at t1 translates to:
      t0              t1        t2        t3
       |_______________|_________|_________|
    A single config can only delay work once
    """

    delay: int


class DropLoopConfig(BaseModel):
    """
    This config describes the number of times to drop periodic work.
    We will still schedule subsequent periodic work with the same phase.
    For example if a node nominally execute periodic work as:
      t0        t1        t2        t3
       |_________|_________|_________|
    Dropping two periodic work at t1 translates to:
      t0                             t3
       |_____________________________|
    A single config can only delay work once
    """

    drop: int


class FaultInjectionConfig(BaseModel):
    # target node name
    inject_to: str
    # when to inject
    inject_at: int
    affect_publish: DropPublishConfig | MutatePublishConfig | None = None
    affect_receive: DropReceiveConfig | DelayReceiveConfig | None = None
    affect_loop: DelayLoopConfig | DropLoopConfig | None = None

    def dump(self, index: int, output: str):
        """
        Dump the fault injection event to a CSV file.

        The CSV file will have two columns: index and time. The index
        represents the node index that was injected, and the time
        represents when the event was injected.

        If the file already exists, it will be overwritten.

        :param index: The index of the node (usually from Graph.node_index).
        :param output: The path to the output file.
        """
        output = os.path.expanduser(output)
        if os.path.exists(output):
            os.remove(output)
        with open(output, mode="a", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([index, self.inject_at])
