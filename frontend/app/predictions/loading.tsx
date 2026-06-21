import { SkeletonPage } from "@/components/common/Skeleton"

export default function PredictionsLoading() {
  return <SkeletonPage title="My picks & track record" cards={8} />
}
