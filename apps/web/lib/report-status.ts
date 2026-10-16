export const REPORT_STATUS_VI: Record<string, { label: string; tone: string }> = {
  draft: { label: "Bản nháp", tone: "gray" },
  approved: { label: "Đã duyệt, đang gửi", tone: "blue" },
  sent: { label: "Đã gửi", tone: "green" },
  partially_sent: { label: "Gửi một phần", tone: "yellow" },
  failed: { label: "Gửi lỗi", tone: "red" },
  superseded: { label: "Đã thay", tone: "gray" },
};
