"""SkySynth llm-router task adapter for CORAL.

Two processes, one boundary. The **trusted** process runs upstream's replay
unchanged, holds the full request (including ground-truth ``quality``), the
clock, billing and the fleet. The **candidate** process runs the submitted
policy pair under a deny-default OS sandbox and sees only a serialized public
request and public fleet view. ``bridge.RemotePairRouter`` is the upstream
``Router`` that forwards each callback across that boundary.
"""
