// The analyst workspace no longer exposes synthetic event-injection controls.
export async function getServerSideProps() {
  return { redirect: { destination: '/', permanent: false } }
}
export default function RetiredDemoPage() { return null }
