/**
 * ErrorList Component
 *
 * Pure presentational component for displaying a list of validation errors.
 * Follows Single Responsibility Principle - only concerned with rendering errors.
 */
export function ErrorList({ errors }) {
  if (!errors || errors.length === 0) {
    return null;
  }

  return (
    <ul className="list-disc list-inside space-y-1">
      {errors.map((error, index) => (
        <li key={index}>
          <strong>{error.type}:</strong> {error.message}
        </li>
      ))}
    </ul>
  );
}
