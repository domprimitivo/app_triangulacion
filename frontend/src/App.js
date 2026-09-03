import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import "@/App.css";
import { Navbar } from './components/Navbar';
import { HeroSection } from './components/HeroSection';
import { ProblemSection } from './components/ProblemSection';
import { SolutionSection } from './components/SolutionSection';
import { DomainsSection } from './components/DomainsSection';
import { HowItWorksSection } from './components/HowItWorksSection';
import { DifferentiatorsSection } from './components/DifferentiatorsSection';
import { RoadmapSection } from './components/RoadmapSection';
import { PricingSection } from './components/PricingSection';
import { FAQSection } from './components/FAQSection';
import { CTAFinalSection } from './components/CTAFinalSection';
import { RegisterModal } from './components/RegisterModal';
import { Footer } from './components/Footer';
import { PantallaClaridad } from './components/PantallaClaridad';
import { ArchivosEmbudo } from './components/ArchivosEmbudo';
import { CiberModo1 } from './components/CiberModo1';
import { trackEvent, EVENTS } from './lib/analytics';

function Landing() {
  const [isRegisterOpen, setIsRegisterOpen] = useState(false);
  const [selectedDomain, setSelectedDomain] = useState(null);

  const handleOpenRegister = (domain = null) => {
    trackEvent(EVENTS.REGISTER_OPEN, { domain });
    setSelectedDomain(domain);
    setIsRegisterOpen(true);
  };

  const handleCloseRegister = () => {
    setIsRegisterOpen(false);
    setSelectedDomain(null);
  };

  const handleDomainSelect = (domainId) => {
    handleOpenRegister(domainId);
  };

  return (
    <div className="min-h-screen bg-[#09090B]" data-testid="app-container">
      <Navbar onRegisterClick={() => handleOpenRegister()} />
      
      <main>
        <HeroSection onRegisterClick={() => handleOpenRegister()} />
        <ProblemSection />
        <SolutionSection />
        <DomainsSection onDomainSelect={handleDomainSelect} />
        <HowItWorksSection />
        <DifferentiatorsSection />
        <RoadmapSection />
        <PricingSection onRegisterClick={() => handleOpenRegister()} />
        <FAQSection />
        <CTAFinalSection onRegisterClick={() => handleOpenRegister()} />
      </main>

      <Footer />

      <RegisterModal 
        isOpen={isRegisterOpen}
        onClose={handleCloseRegister}
        preselectedDomain={selectedDomain}
      />
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/claridad" element={<PantallaClaridad />} />
        <Route path="/archivos" element={<ArchivosEmbudo />} />
        <Route path="/ciberseguridad" element={<CiberModo1 />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
