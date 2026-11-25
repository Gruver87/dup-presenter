import { DupPresenterComposition } from "./Composition";
import { DupThumbnailComposition } from "./Thumbnail";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <DupPresenterComposition />
      <DupThumbnailComposition />
    </>
  );
};
