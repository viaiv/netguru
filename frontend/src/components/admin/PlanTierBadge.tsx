/**
 * PlanTierBadge — colored chip for plan tiers.
 */
interface IPlanTierBadgeProps {
  tier: string;
}

function PlanTierBadge({ tier }: IPlanTierBadgeProps) {
  return <span className={`chip chip--tier-${tier}`}>{tier}</span>;
}

export default PlanTierBadge;
