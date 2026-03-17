import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import type { Attempt } from "../lib/api";

export const REPLAY_SPEEDS = [1, 2, 5, 10, 20];

export interface ReplayState {
  active: boolean;
  playing: boolean;
  currentIndex: number;
  speed: number;
  totalAttempts: number;
  visibleAttempts: Attempt[];
  latestAttempt: Attempt | null;
  progress: number;
  start: () => void;
  stop: () => void;
  togglePlay: () => void;
  setSpeed: (speed: number) => void;
  seek: (index: number) => void;
  stepForward: () => void;
  stepBack: () => void;
}

export function useReplay(attempts: Attempt[]): ReplayState {
  const [active, setActive] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [speed, setSpeedVal] = useState(5);

  const chronological = useMemo(
    () => [...attempts].sort((a, b) => a.timestamp.localeCompare(b.timestamp)),
    [attempts]
  );

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    if (active && playing) {
      timerRef.current = setInterval(() => {
        setCurrentIndex((prev) => Math.min(prev + 1, chronological.length));
      }, 1000 / speed);
    }

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [active, playing, speed, chronological.length]);

  useEffect(() => {
    if (active && playing && currentIndex >= chronological.length) {
      setPlaying(false);
    }
  }, [active, playing, currentIndex, chronological.length]);

  const start = useCallback(() => {
    if (chronological.length === 0) return;
    setCurrentIndex(0);
    setActive(true);
    setPlaying(true);
  }, [chronological.length]);

  const stop = useCallback(() => {
    setPlaying(false);
    setActive(false);
    setCurrentIndex(0);
  }, []);

  const togglePlay = useCallback(() => {
    if (!playing && currentIndex >= chronological.length) {
      setCurrentIndex(0);
      setPlaying(true);
    } else {
      setPlaying((p) => !p);
    }
  }, [playing, currentIndex, chronological.length]);

  const setSpeed = useCallback((s: number) => setSpeedVal(s), []);

  const seek = useCallback(
    (index: number) => {
      setCurrentIndex(Math.max(0, Math.min(index, chronological.length)));
      setPlaying(false);
    },
    [chronological.length]
  );

  const stepForward = useCallback(() => {
    setCurrentIndex((prev) => Math.min(prev + 1, chronological.length));
    setPlaying(false);
  }, [chronological.length]);

  const stepBack = useCallback(() => {
    setCurrentIndex((prev) => Math.max(prev - 1, 0));
    setPlaying(false);
  }, []);

  const visibleAttempts = active
    ? chronological.slice(0, currentIndex)
    : attempts;

  const latestAttempt =
    active && currentIndex > 0 ? chronological[currentIndex - 1] : null;

  const progress =
    chronological.length > 0 ? currentIndex / chronological.length : 0;

  return {
    active,
    playing,
    currentIndex,
    speed,
    totalAttempts: chronological.length,
    visibleAttempts,
    latestAttempt,
    progress,
    start,
    stop,
    togglePlay,
    setSpeed,
    seek,
    stepForward,
    stepBack,
  };
}
