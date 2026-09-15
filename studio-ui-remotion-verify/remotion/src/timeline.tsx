import React from 'react';
import { AbsoluteFill, Easing, interpolate, Sequence, useCurrentFrame, useVideoConfig } from 'remotion';
import { Audio, Video } from '@remotion/media';

export type NewsFlowSequence = {
  kind: 'intro' | 'footage';
  src: string;
  from: number;
  durationInFrames: number;
  sourceStart?: number;
};

export type NewsFlowRenderProject = {
  fps: number;
  aspectRatio: '16:9' | '9:16' | '1:1';
  durationInFrames: number;
  sequences: NewsFlowSequence[];
  voiceover: { src: string; from: number };
  overlay?: { src: string; position?: string };
  transitionStyle?: 'crossfade' | 'dip-black' | 'cut' | 'slide-left';
  transitionFrames?: number;
};

const asMediaUrl = (value: string) => {
  if (!value) return '';
  if (/^(https?:|file:)/i.test(value)) return value;
  return `file:///${value.replace(/\\/g, '/').replace(/^\/+/, '')}`;
};

const FittedVideo: React.FC<{ sequence: NewsFlowSequence; transitionFrames?: number; transitionStyle?: NewsFlowRenderProject['transitionStyle'] }> = ({ sequence, transitionFrames = 0, transitionStyle = 'crossfade' }) => {
  const { fps } = useVideoConfig();
  const frame = useCurrentFrame();
  const trimBefore = Math.max(0, Math.floor((sequence.sourceStart || 0) * fps));
  const transition = transitionFrames > 0 ? interpolate(frame, [0, transitionFrames], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(0.16, 1, 0.3, 1),
  }) : 1;
  const fade = transitionStyle === 'cut' ? 1 : transition;
  const translateX = transitionStyle === 'slide-left' && transitionFrames > 0
    ? interpolate(frame, [0, transitionFrames], [100, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }) : 0;
  const dipOpacity = transitionStyle === 'dip-black' && transitionFrames > 0 ? transition : 1;
  const scale = sequence.kind === 'intro' ? 1 : interpolate(frame, [0, Math.max(1, sequence.durationInFrames)], [1.035, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  return (
    <AbsoluteFill style={{ backgroundColor: '#000', overflow: 'hidden' }}>
      <Video
        src={asMediaUrl(sequence.src)}
        trimBefore={trimBefore}
        objectFit={sequence.kind === 'intro' ? 'contain' : 'cover'}
        volume={sequence.kind === 'intro' ? 1 : 0}
        style={{ width: '100%', height: '100%', opacity: fade * dipOpacity, scale, transform: `translateX(${translateX}%) scale(${scale})` }}
      />
    </AbsoluteFill>
  );
};

/**
 * NewsFlow's actual Remotion timeline. Footage timing comes from the Python
 * planner, while Remotion owns sequencing, visual composition and MP4 output.
 */
export const NewsFlowMontage: React.FC<{ project: NewsFlowRenderProject }> = ({ project }) => (
  <AbsoluteFill style={{ backgroundColor: '#000' }}>
    {project.sequences.map((sequence, index) => {
      const transitionFrames = index > 0 && project.transitionStyle !== 'cut'
        ? Math.min(project.transitionFrames ?? 7, Math.floor(sequence.durationInFrames / 4)) : 0;
      {/* Start the incoming shot early for the transition, but never extend
          it beyond its verified source duration: Remotion would otherwise
          hold the final frame after a 6-second footage clip ended. */}
      return <Sequence key={`${sequence.src}-${index}`} from={Math.max(0, sequence.from - transitionFrames)} durationInFrames={sequence.durationInFrames}>
        <FittedVideo sequence={sequence} transitionFrames={transitionFrames} transitionStyle={project.transitionStyle} />
      </Sequence>
    })}
    {project.voiceover?.src ? (
      <Sequence from={Math.max(0, project.voiceover.from || 0)}>
        <Audio src={asMediaUrl(project.voiceover.src)} />
      </Sequence>
    ) : null}
  </AbsoluteFill>
);
