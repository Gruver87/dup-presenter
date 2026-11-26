import React from "react";
import {
  AbsoluteFill,
  Audio,
  CalculateMetadataFunction,
  Composition,
  Sequence,
  interpolate,
  staticFile,
} from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide as slideTransition } from "@remotion/transitions/slide";
import { wipe } from "@remotion/transitions/wipe";
import { QuantumWarpBackdrop } from "./CosmosBackdrop";
import { LedgerLayersSlide, MeshNetworkSlide, ProtocolCosmosSlide, TxJourneySlide } from "./StorySlides";
import { BRollCinematicSlide, ChartStorySlide, CinemaClipSlide, StatBurstSlide, VersusSplitSlide, computeSlideLocalDuck } from "./UniversalSlides";
import { ResolvedSlide } from "./types";
import { Aurora3DBackdrop } from "./composition/aurora3d";
import { CaptionOverlay, ProgressBar } from "./composition/captions";
import { BG, DECK, DURATION, FPS, HEIGHT, IS_PORTRAIT, IS_QUANTUM, THEME, TRANSITION_FRAMES, TRANSITION_STYLE, WIDTH, computeDuckFactor } from "./composition/deckContext";
import { SlideChrome } from "./composition/primitives";
import { ArchFlowSlide, CodeSplitSlide, Hero3DSlide, KpiSlide, Outro3DSlide, QuoteSlide, ScreenSplitSlide, TerminalSlide, TimelineSlide, UiRecordingSlide } from "./composition/slides3d";
import { StockBackdrop } from "./composition/stockBackdrop";

type Props = Record<string, unknown>;

const calculateMetadata: CalculateMetadataFunction<Props> = () => ({
  durationInFrames: DURATION,
  fps: FPS,
  width: WIDTH,
  height: HEIGHT,
});

const renderSlideTransition = (idx: number, key: string) => {
  const timing = linearTiming({ durationInFrames: TRANSITION_FRAMES });
  if (TRANSITION_STYLE === "slide") {
    return (
      <TransitionSeries.Transition
        key={key}
        presentation={slideTransition({ direction: idx % 2 === 0 ? "from-right" : "from-bottom" })}
        timing={timing}
      />
    );
  }
  if (TRANSITION_STYLE === "wipe") {
    return <TransitionSeries.Transition key={key} presentation={wipe({ direction: "from-left" })} timing={timing} />;
  }
  return <TransitionSeries.Transition key={key} presentation={fade()} timing={timing} />;
};

export const DupPresenter: React.FC<Props> = () => {
  const showCaptions = DECK.burn_captions !== false;
  const sfxEnabled = DECK.sfx_enabled !== false;
  const sfxVolume = DECK.sfx_volume ?? 0.22;
  const duckRatio = DECK.music_duck_ratio ?? 0.36;

  // Transition SFX trigger frames on the master timeline
  const transitionSoundFrames: number[] = [];
  if (sfxEnabled && DECK.sfx_transition_file && TRANSITION_FRAMES > 0) {
    let cursor = 0;
    for (let i = 0; i < DECK.slides.length - 1; i++) {
      cursor += Math.max(1, Math.round(DECK.slides[i].duration_sec * FPS)) - TRANSITION_FRAMES;
      transitionSoundFrames.push(Math.max(0, cursor - 2));
    }
  }

  const renderSlideBody = (slide: ResolvedSlide, durationInFrames: number): React.ReactNode => {
    if (slide.type === "hero_3d") return <Hero3DSlide slide={slide} />;
    if (slide.type === "code_split") return <CodeSplitSlide slide={slide} />;
    if (slide.type === "screen_split") return <ScreenSplitSlide slide={slide} dur={durationInFrames} />;
    if (slide.type === "ui_recording") return <UiRecordingSlide slide={slide} />;
    if (slide.type === "arch_flow") return <ArchFlowSlide slide={slide} />;
    if (slide.type === "outro_3d") return <Outro3DSlide slide={slide} />;
    if (slide.type === "timeline") return <TimelineSlide slide={slide} />;
    if (slide.type === "terminal") return <TerminalSlide slide={slide} />;
    if (slide.type === "kpi") return <KpiSlide slide={slide} />;
    if (slide.type === "quote") return <QuoteSlide slide={slide} />;
    if (slide.type === "ledger_layers") {
      return <LedgerLayersSlide slide={slide} dur={durationInFrames} theme={THEME} isPortrait={IS_PORTRAIT} lang={DECK.lang} />;
    }
    if (slide.type === "tx_journey") {
      return <TxJourneySlide slide={slide} dur={durationInFrames} theme={THEME} isPortrait={IS_PORTRAIT} />;
    }
    if (slide.type === "mesh_network") {
      return <MeshNetworkSlide slide={slide} dur={durationInFrames} theme={THEME} isPortrait={IS_PORTRAIT} />;
    }
    if (slide.type === "protocol_cosmos") {
      return <ProtocolCosmosSlide slide={slide} dur={durationInFrames} theme={THEME} isPortrait={IS_PORTRAIT} />;
    }
    if (slide.type === "versus_split") {
      return <VersusSplitSlide slide={slide} dur={durationInFrames} theme={THEME} isPortrait={IS_PORTRAIT} />;
    }
    if (slide.type === "chart_story") {
      return <ChartStorySlide slide={slide} dur={durationInFrames} theme={THEME} isPortrait={IS_PORTRAIT} />;
    }
    if (slide.type === "stat_burst") {
      return <StatBurstSlide slide={slide} dur={durationInFrames} theme={THEME} isPortrait={IS_PORTRAIT} />;
    }
    if (slide.type === "broll_cinematic") {
      return <BRollCinematicSlide slide={slide} dur={durationInFrames} theme={THEME} isPortrait={IS_PORTRAIT} />;
    }
    if (slide.type === "cinema_clip") {
      return (
        <CinemaClipSlide
          slide={slide}
          dur={durationInFrames}
          theme={THEME}
          isPortrait={IS_PORTRAIT}
          duckRatio={duckRatio}
        />
      );
    }
    return null;
  };

  const renderSlideContent = (slide: ResolvedSlide, durationInFrames: number, hasTransition: boolean) => {
    const voiceDelayFrames = Math.max(0, Math.round((slide.voice_delay_sec ?? 0) * FPS));
    const wantsPop =
      sfxEnabled &&
      Boolean(DECK.sfx_pop_file) &&
      (slide.type === "kpi" || slide.type === "terminal" || slide.type === "hero_3d");
    const slideSfxCues = slide.sfx ?? [];
    return (
      <>
        {slide.type === "cinema_clip" ? (
          renderSlideBody(slide, durationInFrames)
        ) : (
          <>
            <StockBackdrop slide={slide} dur={durationInFrames} />
            <SlideChrome
              brand={DECK.brand}
              num={slide.num}
              tag={slide.tag}
              dur={durationInFrames}
              hasTransition={hasTransition}
            >
              {renderSlideBody(slide, durationInFrames)}
            </SlideChrome>
          </>
        )}
        {showCaptions && <CaptionOverlay captions={slide.captions} style={DECK.caption_style ?? "box"} />}
        <Sequence from={voiceDelayFrames}>
          <Audio src={staticFile(slide.voice_file)} startFrom={0} />
        </Sequence>
        {wantsPop && DECK.sfx_pop_file && (
          <Sequence from={Math.min(8, Math.max(0, durationInFrames - 6))} durationInFrames={15}>
            <Audio src={staticFile(DECK.sfx_pop_file)} volume={sfxVolume * 0.7} />
          </Sequence>
        )}
        {slideSfxCues.map((cue, qIdx) => {
          const fromFrame = Math.min(Math.max(0, Math.round(cue.at_sec * FPS)), Math.max(0, durationInFrames - 1));
          const maxAvail = Math.max(1, durationInFrames - fromFrame);
          const cueDur =
            typeof cue.duration_sec === "number" && cue.duration_sec > 0
              ? Math.min(maxAvail, Math.max(1, Math.round(cue.duration_sec * FPS)))
              : maxAvail;
          const baseVol = typeof cue.volume === "number" && cue.volume > 0 ? cue.volume : 0.4;
          const sfxDuck = Math.max(0.45, duckRatio);
          return (
            <Sequence key={`slide-sfx-${slide.id}-${qIdx}`} from={fromFrame} durationInFrames={cueDur}>
              <Audio
                src={staticFile(cue.src)}
                volume={(f) => baseVol * computeSlideLocalDuck(cue.at_sec + f / FPS, slide.speech_windows, sfxDuck)}
              />
            </Sequence>
          );
        })}
      </>
    );
  };

  return (
    <AbsoluteFill style={{ backgroundColor: BG }}>
      {IS_QUANTUM ? <QuantumWarpBackdrop width={WIDTH} height={HEIGHT} /> : <Aurora3DBackdrop />}
      <Audio
        src={staticFile(DECK.ambient_file)}
        volume={(f) => (DECK.voice?.ambient_volume ?? 0.16) * computeDuckFactor(f, Math.max(0.55, duckRatio))}
      />
      {DECK.music_file && (
        <Audio
          src={staticFile(DECK.music_file)}
          volume={(f) => {
            const v = DECK.music_volume ?? 0.12;
            const fadeLen = Math.min(2 * FPS, Math.floor(DURATION / 3));
            const env =
              fadeLen > 0
                ? interpolate(f, [0, fadeLen, DURATION - fadeLen, DURATION], [0, v, v, 0], {
                    extrapolateLeft: "clamp",
                    extrapolateRight: "clamp",
                  })
                : v;
            return env * computeDuckFactor(f, duckRatio);
          }}
        />
      )}
      {transitionSoundFrames.map((tf, idx) => (
        <Sequence key={`sfx-tr-${idx}`} from={tf} durationInFrames={Math.max(12, TRANSITION_FRAMES + 6)}>
          <Audio src={staticFile(DECK.sfx_transition_file!)} volume={sfxVolume} />
        </Sequence>
      ))}
      {TRANSITION_FRAMES > 0 ? (
        <TransitionSeries>
          {DECK.slides.map((slide, idx) => {
            const durationInFrames = Math.max(TRANSITION_FRAMES * 2 + 1, Math.round(slide.duration_sec * FPS));
            return (
              <React.Fragment key={slide.id}>
                <TransitionSeries.Sequence durationInFrames={durationInFrames}>
                  {renderSlideContent(slide, durationInFrames, true)}
                </TransitionSeries.Sequence>
                {idx < DECK.slides.length - 1 && renderSlideTransition(idx, `tr-${slide.id}`)}
              </React.Fragment>
            );
          })}
        </TransitionSeries>
      ) : (
        (() => {
          let offset = 0;
          return DECK.slides.map((slide) => {
            const from = offset;
            const durationInFrames = Math.max(1, Math.round(slide.duration_sec * FPS));
            offset += durationInFrames;
            return (
              <Sequence key={slide.id} from={from} durationInFrames={durationInFrames}>
                {renderSlideContent(slide, durationInFrames, false)}
              </Sequence>
            );
          });
        })()
      )}
      <ProgressBar />
    </AbsoluteFill>
  );
};

export const DupPresenterComposition = () => (
  <Composition
    id="DupPresenter"
    component={DupPresenter}
    durationInFrames={DURATION}
    fps={FPS}
    width={WIDTH}
    height={HEIGHT}
    calculateMetadata={calculateMetadata}
  />
);
