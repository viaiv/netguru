/**
 * UserRoleBadge — colored chip for user roles.
 */
interface IUserRoleBadgeProps {
  role: string;
}

function UserRoleBadge({ role }: IUserRoleBadgeProps) {
  return <span className={`chip chip--role-${role}`}>{role}</span>;
}

export default UserRoleBadge;
