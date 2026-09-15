import React from 'react';
import { Composition } from 'remotion';
import { NewsFlowMontage, type NewsFlowRenderProject } from './timeline';

const emptyProject: NewsFlowRenderProject = {
  fps: 30,
  aspectRatio: '16:9',
  durationInFrames: 1,
  sequences: [],
  voiceover: { src: '', from: 0 },
  overlay: { src: '', position: 'bottom' },
};

/** The actual composition that is rendered by the NewsFlow core. */
export const NewsFlowRoot: React.FC = () => (
  <>
    <Composition
      id="NewsFlowMontage16x9"
      component={NewsFlowMontage}
      durationInFrames={36000}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{ project: emptyProject }}
    />
    <Composition
      id="NewsFlowMontage9x16"
      component={NewsFlowMontage}
      durationInFrames={36000}
      fps={30}
      width={1080}
      height={1920}
      defaultProps={{ project: { ...emptyProject, aspectRatio: '9:16' } }}
    />
    <Composition
      id="NewsFlowMontage1x1"
      component={NewsFlowMontage}
      durationInFrames={36000}
      fps={30}
      width={1080}
      height={1080}
      defaultProps={{ project: { ...emptyProject, aspectRatio: '1:1' } }}
    />
  </>
);
