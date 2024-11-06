import csv
import os

from strict_base_model import StrictBaseModel


class DropPublishConfig(StrictBaseModel):
    """
    This config describes which topic to drop and how many times.
    """

    topic: str
    drop: int


class MutatePublishConfig(StrictBaseModel):
    """
    This config describes which topic to mutate and use what value.
    """

    topic: str
    value: int
    count: int = 1


class DropReceiveConfig(StrictBaseModel):
    """
    This config describes which topic to drop received messages from and how many times.
    """

    topic: str
    drop: int


class DelayReceiveConfig(StrictBaseModel):
    """
    This config describes which topic to delay a received message.
    It only delays a single instance.
    """

    topic: str
    delay: int
    count: int = 1


class DelayLoopConfig(StrictBaseModel):
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
    count: int = 1


class DropLoopConfig(StrictBaseModel):
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


class FaultConfig(StrictBaseModel):
    # target node name
    inject_to: str | None = None
    # when to inject
    inject_at: int | None = None
    affect_publish: DropPublishConfig | MutatePublishConfig | None = None
    affect_receive: DropReceiveConfig | DelayReceiveConfig | None = None
    affect_loop: DelayLoopConfig | DropLoopConfig | None = None
    # crash a node
    crash: bool | None = None

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
