import { createTheme, rem } from "@mantine/core";

export const theme = createTheme({
  primaryColor: "opsBlue",
  fontFamily:
    "Inter, Pretendard, system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
  headings: {
    fontFamily:
      "Inter, Pretendard, system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
    fontWeight: "650",
  },
  defaultRadius: "md",
  radius: {
    xs: rem(3),
    sm: rem(5),
    md: rem(7),
    lg: rem(8),
    xl: rem(10),
  },
  colors: {
    opsBlue: [
      "#edf5ff",
      "#d9e8ff",
      "#b3d0ff",
      "#89b6f8",
      "#669fee",
      "#4f90e8",
      "#4288e6",
      "#3476cc",
      "#2b68b8",
      "#1d5aa3",
    ],
  },
});

