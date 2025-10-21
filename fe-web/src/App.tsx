import { useLocation, Routes, Route } from "react-router-dom";
import Join from "./pages/Join";


export default function App() {
  const location = useLocation();

  return (
    <>
      <Routes>
        <Route path="/" element={<Join />} />
      </Routes>
    </>
  );
}
