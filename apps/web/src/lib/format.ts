export const money = (value: string | null | undefined): string =>
  value === null || value === undefined
    ? "N/A"
    : `$${Number(value).toFixed(2)}`;

export const percent = (value: string | null): string =>
  value === null ? "N/A" : `${(Number(value) * 100).toFixed(1)}%`;
