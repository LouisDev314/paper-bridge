'use client';

import { useEffect, useState } from 'react';

export default function Home() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    fetch('http://localhost:8000/health')
      .then((res) => res.json())
      .then(setData)
      .catch(console.error);
  }, []);

  return (
    <main style={{ padding: 40 }}>
      <h1>PaperBridge</h1>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </main>
  );
}